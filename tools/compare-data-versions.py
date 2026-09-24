#!/usr/bin/env python3
"""Compares a new data.clementine-player.org version against the live one.

Hits every route on both hosts and compares what they return by meaning
(parsed XML/JSON, redirect targets), not byte-for-byte, so template
whitespace and equivalent date formats don't show up as differences.
Standard library only.

    python3 tools/compare-data-versions.py \
        --new https://VERSION-dot-clementine-data.appspot.com

Use the "-dot-" hostname for the new version: the *.appspot.com wildcard
certificate doesn't cover VERSION.clementine-data.appspot.com over HTTPS.

Side effects: fetching /sparkle and /sparkle-windows enqueues a counters
task on each host (the same as any real client update check), keyed by the
first word of the User-Agent. This script sends "compare-legacy/1" to the
legacy host and "compare-gen2/1" to the new one. A Counter entity named
"compare-gen2/1" showing up in Datastore shortly afterwards proves the new
version's whole task path works end to end: Cloud Tasks enqueue, routing
back to that version, and its /_tasks/counters handler.
"""
import argparse
import datetime
import email.utils
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

RAINYMOOD_URLS = {'http://images.clementine-player.org/RainyMood.mp3',
                  'http://cloud.clementine-player.org/RainyMood.mp3'}
SPARKLE_NS = '{http://www.andymatuschak.org/xml-namespaces/sparkle}'


class _NoRedirect(urllib.request.HTTPRedirectHandler):
  def redirect_request(self, *args, **kwargs):
    return None


_opener = urllib.request.build_opener(_NoRedirect)


def fetch(base, path, method='GET', headers=None):
  req = urllib.request.Request(base + path, method=method, headers=headers or {})
  req.add_header('User-Agent', req.headers.get('User-agent', 'compare-script/1'))
  try:
    with _opener.open(req, timeout=30) as resp:
      return resp.status, resp.headers, resp.read()
  except urllib.error.HTTPError as e:
    return e.code, e.headers, e.read()
  except (urllib.error.URLError, OSError) as e:
    return None, {}, str(e).encode()


def parse_sparkle(body):
  root = ET.fromstring(body)
  items = []
  for item in root.iter('item'):
    def text(tag):
      el = item.find(tag)
      return (el.text or '').strip() if el is not None else None

    pub = text('pubDate')
    if pub:
      dt = email.utils.parsedate_to_datetime(pub)
      if dt.tzinfo is None:  # "-0000" parses as naive; it means UTC.
        dt = dt.replace(tzinfo=datetime.timezone.utc)
      pub = dt.isoformat()
    enclosure = item.find('enclosure')
    items.append({
        'title': text('title'),
        'minimumSystemVersion': text(SPARKLE_NS + 'minimumSystemVersion'),
        'releaseNotesLink': text(SPARKLE_NS + 'releaseNotesLink'),
        'description': text('description'),
        'pubDate': pub,
        'enclosure': ({k: v.strip() for k, v in enclosure.attrib.items()}
                      if enclosure is not None else None),
    })
  return items


def parse_downloadcount(body):
  releases = {}
  for block in re.findall(r'<div class="release">(.*?)</div>\s*</div>\s*</div>', body.decode(), re.S):
    spans = re.findall(r'<span class="name">(.*?)</span>\s*<span>(\d+)</span>', block, re.S)
    if spans:
      releases[spans[0][0].strip()] = {n.strip(): int(c) for n, c in spans[1:]}
  return releases


results = []


def report(status, route, detail=''):
  results.append(status)
  print('%-9s %-40s %s' % (status, route, detail))


def compare_redirect(legacy, new, path):
  ls, lh, _ = fetch(legacy, path)
  ns, nh, _ = fetch(new, path)
  ll, nl = lh.get('Location'), nh.get('Location')
  if ls == ns and ll == nl:
    report('PASS', path, '%s -> %s' % (ns, nl))
  elif path == '/rainymood' and ls == ns == 302 and {ll, nl} <= RAINYMOOD_URLS:
    # Which of the two it picks comes from a cron health check, and cron
    # only runs on the version serving default traffic.
    report('WARN', path, 'legacy -> %s | new -> %s (new version\'s health-check '
           'cron only runs once it\'s promoted)' % (ll, nl))
  else:
    report('FAIL', path, 'legacy %s %s | new %s %s' % (ls, ll, ns, nl))


def compare_sparkle(legacy, new, path):
  ls, lh, lb = fetch(legacy, path, headers={'User-Agent': 'compare-legacy/1 Sparkle/1'})
  ns, nh, nb = fetch(new, path, headers={'User-Agent': 'compare-gen2/1 Sparkle/1'})
  if ls != 200 or ns != 200:
    report('FAIL', path, 'legacy %s | new %s' % (ls, ns))
    return
  if not nh.get('Content-Type', '').startswith('text/xml'):
    report('FAIL', path, 'new Content-Type %r' % nh.get('Content-Type'))
    return
  try:
    litems, nitems = parse_sparkle(lb), parse_sparkle(nb)
  except ET.ParseError as e:
    report('FAIL', path, 'XML parse error: %s' % e)
    return
  if litems == nitems:
    report('PASS', path, '%d items identical' % len(nitems))
    return
  report('FAIL', path, 'legacy %d items | new %d items' % (len(litems), len(nitems)))
  for i, (a, b) in enumerate(zip(litems, nitems)):
    for field in a:
      if a[field] != b[field]:
        print('          item %d %s: legacy %r | new %r' % (i, field, a[field], b[field]))
  if sorted(map(repr, litems)) == sorted(map(repr, nitems)):
    print('          (same items, different order)')


def compare_json(legacy, new, path, warn_only=False):
  ls, _, lb = fetch(legacy, path)
  ns, _, nb = fetch(new, path)
  if ls == ns and lb == nb:
    report('PASS', path, '%s, bodies byte-identical' % ns)
    return
  try:
    lj, nj = json.loads(lb), json.loads(nb)
  except ValueError:
    if ls == ns and ls != 200:
      # e.g. /geolocate 404s on both when App Engine attaches no geo headers
      # for this client; only the framework's error page differs.
      report('WARN', path, 'both %s (not exercised from this client)' % ns)
    else:
      report('FAIL', path, 'non-JSON response: legacy %s | new %s' % (ls, ns))
    return
  if ls == ns and lj == nj:
    report('PASS', path, '%s, bodies identical' % ns)
  else:
    # The proxy routes cache backend responses, so legacy may be serving an
    # older cached copy than the new version fetched fresh.
    report('WARN' if warn_only and ns == 200 else 'FAIL', path,
           'legacy %s (%d bytes) | new %s (%d bytes), bodies differ'
           % (ls, len(lb), ns, len(nb)))


def compare_downloadcount(legacy, new, path):
  ls, _, lb = fetch(legacy, path)
  ns, _, nb = fetch(new, path)
  if ns != 200:
    report('FAIL', path, 'legacy %s | new %s: %s' % (ls, ns, nb[:200]))
    return
  if ls != 200:
    report('WARN', path, 'new 200 but legacy %s, nothing to compare against' % ls)
    return
  lr, nr = parse_downloadcount(lb), parse_downloadcount(nb)
  if set(lr) != set(nr):
    report('FAIL', path, 'release lists differ: only legacy %s, only new %s'
           % (sorted(set(lr) - set(nr))[:5], sorted(set(nr) - set(lr))[:5]))
  elif any(set(lr[r]) != set(nr[r]) for r in lr):
    report('FAIL', path, 'file lists differ within a release')
  else:
    # Counts can tick up between the two requests; only flag a decrease.
    # GitHub's API can serve slightly stale counts from different caches, so
    # a small difference either way isn't a regression.
    shrunk = [(r, f) for r in lr for f in lr[r] if nr[r][f] < lr[r][f]]
    report('WARN' if shrunk else 'PASS', path,
           '%d releases, same files%s' % (len(nr), ', some counts lower on new (GitHub API '
                                          'cache skew; rerun to confirm): %s' % shrunk[:2] if shrunk else ''))


def compare_favicon(legacy, new, path):
  ls, _, lb = fetch(legacy, path)
  ns, _, nb = fetch(new, path)
  same = hashlib.sha256(lb).digest() == hashlib.sha256(nb).digest()
  report('PASS' if ls == ns == 200 and same else 'FAIL', path,
         'legacy %s | new %s | %s' % (ls, ns, 'same bytes' if same else 'bytes differ'))


def expect_new(new, path, allowed, why, method='GET', headers=None):
  ns, nh, _ = fetch(new, path, method=method, headers=headers)
  report('EXPECTED' if ns in allowed else 'FAIL', path,
         'new %s (want %s): %s' % (ns, '/'.join(map(str, allowed)), why))


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument('--legacy', default='https://data.clementine-player.org')
  parser.add_argument('--new', required=True)
  args = parser.parse_args()
  legacy, new = args.legacy.rstrip('/'), args.new.rstrip('/')
  print('legacy: %s\nnew:    %s\n' % (legacy, new))

  compare_sparkle(legacy, new, '/sparkle')
  compare_sparkle(legacy, new, '/sparkle-windows')
  for path in ('/', '/rainymood', '/icecast-directory', '/oauth?port=1234&code=abc',
               '/skydrive?state=5678&code=def', '/.well-known/acme-challenge/compare-test'):
    compare_redirect(legacy, new, path)
  compare_json(legacy, new, '/geolocate')
  compare_json(legacy, new, '/fetchbio?artist=Radiohead&lang=en', warn_only=True)
  compare_json(legacy, new, '/fetchimages?artist=Radiohead', warn_only=True)
  compare_downloadcount(legacy, new, '/downloadcount')
  compare_favicon(legacy, new, '/favicon.ico')

  print()
  expect_new(new, '/versions', {410}, 'publishing page stubbed out')
  expect_new(new, '/counters', {404}, 'dropped (its charting APIs were shut down)')
  expect_new(new, '/c2dm/list', {404}, 'dropped (C2DM is dead)')
  expect_new(new, '/_tasks/rainymood', {403}, 'cron-only, rejected from outside')
  # App Engine strips these headers from external requests, so spoofing them
  # must still be rejected. A 200 here would mean anyone could trigger tasks.
  expect_new(new, '/_tasks/rainymood', {403}, 'spoofed cron header rejected',
             headers={'X-Appengine-Cron': 'true'})
  expect_new(new, '/_tasks/counters', {403}, 'spoofed queue header rejected',
             method='POST', headers={'X-AppEngine-QueueName': 'default',
                                     'Content-Type': 'application/x-www-form-urlencoded'})

  failed = results.count('FAIL')
  print('\n%d checks: %d pass, %d expected differences, %d warnings, %d failures'
        % (len(results), results.count('PASS'), results.count('EXPECTED'),
           results.count('WARN'), failed))
  print('\nThen check Datastore for a Counter entity named "compare-gen2/1" '
        '(may take a minute) to confirm the new version\'s task path end to end.')
  return 1 if failed else 0


if __name__ == '__main__':
  sys.exit(main())
