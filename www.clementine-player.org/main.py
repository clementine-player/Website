# -*- coding: utf-8 -*-

import base64
import hashlib
import copy
import datetime
import json
import logging
import os
import re
import time

import babel
import babel.dates
import babel.support
import requests
from flask import Flask, Response, redirect, request
from google.cloud import datastore
from werkzeug.routing import BaseConverter

from data import LANGUAGE_NAMES
from data import LANGUAGES
from data import ANDROID_HOME_SCREENSHOTS
from data import NEWS
from data import RELEASE_PLATFORMS
from data import RELEASE_SCREENSHOTS
from data import SCREENSHOTS

import android
import thumbnailer as thumbnailer_module
from thumbnailer import thumbnailer

RELEASES_KEY = 'github_releases'
RELEASES_CACHE_SECONDS = 60 * 60
ANDROID_SCREENSHOTS_KEY = 'android_screenshots'
# A screenshot on a Clementine release: screenshot-<platform>-<screen>.png.
RELEASE_SCREENSHOT = re.compile(r'screenshot-([a-z]+)-([a-z-]+)\.png$')
# After a failed fetch, how long until the next try. The home page shows these,
# so while GitHub is down every view mustn't wait for it again.
ANDROID_RETRY_SECONDS = 5 * 60
DISTRO_CODENAMES_KEY = 'distro_codenames'
# New Debian/Ubuntu codenames appear at most a few times a year, so this
# can be far less fresh than the release cache above.
DISTRO_CODENAMES_CACHE_SECONDS = 60 * 60 * 24 * 7
LOCAL_CACHE_SECONDS = 60

# Section headings for the downloads page, keyed by the base os string
# (before any '-arm64' suffix).
FAMILY_DISPLAY = {
  'debian':  'Debian',
  'fedora':  'Fedora',
  'mac':     'Mac',
  'source':  'Source Code',
  'windows': 'Windows',
  'ubuntu':  'Ubuntu',
}


class Error(Exception):
  pass


class GithubFetchError(Error):
  pass


class LangConverter(BaseConverter):
  # Matches App Engine's original URL scheme: an optional 2-letter language
  # code, optionally with a _REGION or @variant suffix (en, pt_BR, sr@latin).
  regex = r'[a-zA-Z]{2}(?:_[a-zA-Z]{2})?(?:@latin)?'


app = Flask(__name__, template_folder='.')
app.url_map.converters['lang'] = LangConverter
app.register_blueprint(thumbnailer)

# Translated strings in these templates sometimes embed literal HTML (e.g.
# "About &amp; Features" in main.html), pre-escaped by whoever wrote the
# translation. The original app never enabled autoescaping, so keep it off
# here too -- turning it on would double-escape those entities.
app.jinja_env.autoescape = False


def _github_token():
  token = os.environ.get('GITHUB_TOKEN')
  if token:
    return token
  from google.cloud import secretmanager
  client = secretmanager.SecretManagerServiceClient()
  project = os.environ['GOOGLE_CLOUD_PROJECT']
  name = 'projects/%s/secrets/GITHUB_TOKEN/versions/latest' % project
  response = client.access_secret_version(name=name)
  return response.payload.data.decode('utf-8')


GITHUB_TOKEN = _github_token()


def format_datetime(value, language='en'):
  # Babel supports fewer locales than we do so change to English for
  # unsupported locales.
  if not babel.localedata.exists(language):
    language = 'en'
  return babel.dates.format_date(value, format='full', locale=language)


app.jinja_env.filters['datetime'] = format_datetime

_translations_cache = {}


def get_translations(locale):
  if locale not in _translations_cache:
    _translations_cache[locale] = babel.support.Translations.load(
        os.path.join(os.path.dirname(__file__), 'locale'), [locale], domain='django')
  return _translations_cache[locale]


def make_translator(translations):
  # Matches jinja2.ext.i18n's `_()`/`gettext()` global: translated strings
  # can contain %(name)s placeholders, filled in from keyword arguments
  # (e.g. _("Find us on %(site)s.", site="...")).
  def _(message, **kwargs):
    translated = translations.gettext(message)
    return translated % kwargs if kwargs else translated
  return _


_datastore_client = None


def _get_datastore_client():
  global _datastore_client
  if _datastore_client is None:
    _datastore_client = datastore.Client()
  return _datastore_client


# In-process L1 cache: (value, fetched_at, cached_at), keyed the same as
# Datastore. Avoids a Datastore read on every single request within an
# instance's lifetime.
_local_cache = {}


def _read_cache(key):
  local = _local_cache.get(key)
  if local is not None and time.time() - local[2] < LOCAL_CACHE_SECONDS:
    return {'value': local[0], 'fetched_at': local[1]}

  client = _get_datastore_client()
  entity = client.get(client.key('Cache', key))
  if entity is None:
    return None
  _local_cache[key] = (entity['value'], entity['fetched_at'], time.time())
  return {'value': entity['value'], 'fetched_at': entity['fetched_at']}


def _write_cache(key, value, fetched_at):
  client = _get_datastore_client()
  # `value` (the raw GitHub API response) routinely exceeds Datastore's
  # 1500-byte limit for indexed string properties -- exclude it, matching
  # the same treatment thumbnailer.py already gives its image bytes.
  entity = datastore.Entity(client.key('Cache', key), exclude_from_indexes=('value',))
  entity.update({'value': value, 'fetched_at': fetched_at})
  client.put(entity)
  _local_cache[key] = (value, fetched_at, time.time())


def _fetch_release_from_github():
  token = base64.b64encode(('%s:' % GITHUB_TOKEN).encode('utf-8')).decode('ascii')
  # There's no longer an official "latest" release -- releases are rolling
  # now, so /releases/latest (which only ever returns the newest release
  # NOT marked as a prerelease) can point at an arbitrarily old release.
  # Ask for the single newest release instead, published or not.
  r = requests.get(
      'https://api.github.com/repos/clementine-player/Clementine/releases?per_page=1',
      headers={'Authorization': 'Basic %s' % token})
  if r.status_code != 200:
    raise GithubFetchError('Error fetching releases: %d %s' % (r.status_code, r.text))
  releases = r.json()
  if not releases:
    raise GithubFetchError('No releases found')
  return json.dumps(releases[0])


def _release_screenshot_key(asset):
  # What its thumbnail and full size are kept by: its contents' SHA-256, which
  # GitHub gives, so a release whose screenshots didn't change reuses them.
  digest = asset.get('digest') or ''
  if digest.startswith('sha256:'):
    return digest[len('sha256:'):]
  return 'id%d' % asset['id']


def fetch_release_screenshots():
  # Clementine's screenshots on its newest release, as
  # {'version': ..., 'platforms': {platform: {screen: entry}}}, or None.
  try:
    release = _load_release()
  except Exception:
    logging.exception('Failed to load the release for its screenshots')
    return None
  platforms = {}
  for asset in release.get('assets', []):
    m = RELEASE_SCREENSHOT.match(asset['name'].lower())
    if not m:
      continue
    key = _release_screenshot_key(asset)
    platforms.setdefault(m.group(1), {})[m.group(2)] = {
      'thumbnail': '/thumbnails/release/%s.png' % key,
      'full': '/release-screenshots/%s.png' % key,
    }
  if not platforms:
    return None
  return {'version': release['tag_name'], 'platforms': platforms}


def release_screenshot_url(key):
  # Where to download the newest release's screenshot with this key, or None:
  # only its own screenshots are ever fetched.
  try:
    assets = _load_release().get('assets', [])
  except Exception:
    logging.exception('Failed to load the release for its screenshot %s', key)
    return None
  for asset in assets:
    if RELEASE_SCREENSHOT.match(asset['name'].lower()) and _release_screenshot_key(asset) == key:
      return asset['browser_download_url']
  return None


thumbnailer_module.release_screenshot_url = release_screenshot_url


def visitor_platforms(user_agent):
  # The release's platforms in the order to show them: the visitor's first,
  # where the browser says which it's on.
  ua = user_agent.lower()
  order = [p for p, _name in RELEASE_PLATFORMS]
  first = None
  if 'windows' in ua:
    first = 'windows'
  elif ('macintosh' in ua or 'mac os x' in ua) and not any(d in ua for d in ('iphone', 'ipad', 'ipod')):
    first = 'macos'
  elif ('linux' in ua or 'x11' in ua or 'cros' in ua) and 'android' not in ua:
    first = 'linux'
  if first is None:
    return order
  return [first] + [p for p in order if p != first]


def _fetch_android_screenshots_from_github():
  token = base64.b64encode(('%s:' % GITHUB_TOKEN).encode('utf-8')).decode('ascii')
  headers = {'Authorization': 'Basic %s' % token}
  # Its development builds are prereleases, so /releases/latest is the newest
  # real release, the one on Google Play.
  r = requests.get('https://api.github.com/repos/%s/releases/latest' % android.REPO,
                   headers=headers, timeout=10)
  if r.status_code != 200:
    raise GithubFetchError('Error fetching releases: %d %s' % (r.status_code, r.text))
  tag = r.json()['tag_name']
  if not android.TAG.match(tag):
    raise GithubFetchError('Unexpected tag %r' % tag)
  r = requests.get('https://api.github.com/repos/%s/contents/%s' % (android.REPO, android.SCREENSHOTS_PATH),
                   params={'ref': tag}, headers=headers, timeout=10)
  if r.status_code != 200:
    raise GithubFetchError('Error listing screenshots: %d %s' % (r.status_code, r.text))
  numbers = sorted(int(m.group(1)) for m in (android.SCREENSHOT.match(f['name']) for f in r.json()) if m)
  numbers = [n for n in numbers if 1 <= n <= android.MAX_SCREENSHOTS]
  return json.dumps({'tag': tag, 'numbers': numbers})


def fetch_android_screenshots():
  # The newest Clementine Remote release's store screenshots, or None. Only
  # the screenshots page shows them, so they must never take it down.
  now = time.time()
  try:
    cached = _read_cache(ANDROID_SCREENSHOTS_KEY)
  except Exception:
    logging.exception('Failed to read the Android screenshots from the cache')
    cached = None
  if cached is not None and now - cached['fetched_at'] < RELEASES_CACHE_SECONDS:
    content = cached['value']
  else:
    try:
      content = _fetch_android_screenshots_from_github()
      _write_cache(ANDROID_SCREENSHOTS_KEY, content, now)
    except Exception:
      logging.exception('Failed to fetch the Android screenshots')
      # Keep what there was, or nothing, as if fetched just long enough ago to
      # be tried again in ANDROID_RETRY_SECONDS.
      content = cached['value'] if cached is not None else json.dumps({'tag': None, 'numbers': []})
      try:
        _write_cache(ANDROID_SCREENSHOTS_KEY, content,
                     now - RELEASES_CACHE_SECONDS + ANDROID_RETRY_SECONDS)
      except Exception:
        logging.exception('Failed to cache the Android screenshots')

  release = json.loads(content)
  if not release['numbers']:
    return None
  tag = release['tag']
  return {
    'version': tag[1:],
    'entries': [{
      'number': n,
      'thumbnail': '/thumbnails/android/%s/%d.png' % (tag, n),
      'full': android.screenshot_url(tag, n),
    } for n in release['numbers']],
  }


def _fetch_distro_codenames():
  # Maps each known release codename (lowercased, first word only -- see
  # below) to its distro family. Sourced from endoflife.date instead of a
  # hand-maintained list of codenames, which needs a new entry roughly
  # every 6 months (Ubuntu) or 2 years (Debian) and reliably goes stale
  # (see the classification bug this replaced).
  codenames = {}
  for family, url in (
      ('debian', 'https://endoflife.date/api/debian.json'),
      ('ubuntu', 'https://endoflife.date/api/ubuntu.json')):
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    for cycle in r.json():
      codename = cycle.get('codename')
      if not codename:
        continue
      # Debian's codenames are a single Toy Story name ("Bookworm");
      # Ubuntu's are "Adjective Animal" ("Noble Numbat"). Filenames only
      # ever embed the first word, so that's the lookup key.
      codenames[codename.split()[0].lower()] = family
  return codenames


def get_distro_codenames():
  now = time.time()
  cached = _read_cache(DISTRO_CODENAMES_KEY)
  if cached is not None and now - cached['fetched_at'] < DISTRO_CODENAMES_CACHE_SECONDS:
    return json.loads(cached['value'])
  try:
    codenames = _fetch_distro_codenames()
    _write_cache(DISTRO_CODENAMES_KEY, json.dumps(codenames), now)
    return codenames
  except Exception:
    # This only affects Debian/Ubuntu branding, never whether a download
    # works, so it must never take the downloads page down with it. Fall
    # back to whatever's cached (even if stale), or an empty mapping --
    # every codename then defaults to Ubuntu, same as before this existed.
    logging.exception('Failed to fetch distro codenames from endoflife.date')
    return json.loads(cached['value']) if cached is not None else {}


def _load_release():
  # The newest Clementine release, from GitHub's API, cached.
  now = time.time()
  cached = _read_cache(RELEASES_KEY)

  if cached is not None and now - cached['fetched_at'] < RELEASES_CACHE_SECONDS:
    content = cached['value']
  else:
    try:
      content = _fetch_release_from_github()
      _write_cache(RELEASES_KEY, content, now)
    except GithubFetchError:
      if cached is not None:
        # Serve the last-known-good value rather than hard-failing.
        content = cached['value']
      else:
        raise
  return json.loads(content)


def fetch_release():
  result = _load_release()
  distro_codenames = get_distro_codenames()
  downloads = []
  for asset in result['assets']:
    name = asset['name']
    name_lower = name.lower()
    # Fedora's rpmbuild splits debug symbols into their own -debuginfo/
    # -debugsource sub-packages alongside the real one (e.g.
    # "clementine-debuginfo-1.4.1-1.fc39.x86_64.rpm"). They're not
    # something an end user downloading the app wants to see.
    if 'debuginfo' in name_lower or 'debugsource' in name_lower:
      continue
    # Screenshots, for the screenshots: see fetch_release_screenshots().
    if RELEASE_SCREENSHOT.match(name_lower):
      continue
    info = {
      'os': 'Unknown',
      'ver': result['tag_name'],
      'arch': 0,
      'url': asset['browser_download_url'],
    }
    # Classify by filename extension, not GitHub's reported content_type:
    # content_type depends on whatever the uploading tool set (or GitHub's
    # own sniffing) and isn't stable across releases uploaded by different
    # tooling over the years -- assets whose content_type didn't match any
    # of these branches used to fall through with no display_os/os_logo set
    # at all, silently rendering as a blank/broken entry rather than a
    # missing one. Filenames are what the rest of this function already
    # relies on for arch/distro detection, so they're the reliable signal.
    is_arm64 = 'aarch64' in name_lower or 'arm64' in name_lower
    if name_lower.endswith('.rpm'):
      info['os'] = 'fedora'
      info['short_os'] = 'Fedora'
      info['os_logo'] = 'fedora-logo.png'
      if is_arm64:
        info['arch'] = 64
        info['arch_label'] = ARCH_ARM64
      elif 'x86_64' in name:
        info['arch'] = 64
        info['arch_label'] = ARCH_X86_64
      elif 'i686' in name:
        info['arch'] = 32
        info['arch_label'] = ARCH_X86_32
      m = re.search(r'\.fc(\d+)\.', name)
      if m:
        info['display_os'] = 'Fedora %s' % m.group(1)
      else:
        info['display_os'] = 'Fedora'
    elif name_lower.endswith('.dmg'):
      info['os'] = 'mac'
      info['display_os'] = 'Mac'
      info['short_os'] = 'Mac'
      info['os_logo'] = 'leopard-logo.png'
      info['arch'] = 64
      # The DMG's name doesn't say, and CI builds it on Apple Silicon
      # (macos-26-arm64, Homebrew in /opt/homebrew) for Apple Silicon only.
      if 'universal' in name_lower:
        info['arch_label'] = 'Apple Silicon and Intel'
      elif 'intel' in name_lower or 'x86_64' in name_lower:
        info['arch_label'] = 'Intel'
      else:
        info['arch_label'] = 'Apple Silicon'
    elif name_lower.endswith(('.tar.xz', '.tar.gz')):
      info['os'] = 'source'
      info['display_os'] = 'Source Code'
      info['short_os'] = 'Source'
      info['os_logo'] = 'source-logo.png'
    elif name_lower.endswith('.exe'):
      info['os'] = 'windows'
      info['display_os'] = 'Windows'
      info['short_os'] = 'Windows'
      info['os_logo'] = 'windows-logo.png'
      # Windows builds are 64-bit by default these days; only a filename
      # that explicitly says otherwise gets classified as 32-bit.
      if not is_arm64 and ('win32' in name_lower or 'x86' in name_lower or 'i686' in name_lower):
        info['arch'] = 32
        info['arch_label'] = ARCH_X86_32
      else:
        info['arch'] = 64
        info['arch_label'] = ARCH_ARM64 if is_arm64 else ARCH_X86_64
    elif name_lower.endswith('.deb'):
      # Extract the distro codename directly from the filename instead of
      # checking it against a maintained list of known Ubuntu/Debian
      # release names -- that list needs a new entry roughly every 6
      # months (Ubuntu) or 2 years (Debian) and reliably goes stale (see
      # the Fedora/Ubuntu-codename bug this replaced). Package filenames
      # for multi-distro builds conventionally embed the codename as a
      # word immediately before the architecture suffix, e.g.
      # "clementine_1.3.9-jammy1_amd64.deb" -- capture that directly.
      # Which distro family a codename belongs to comes from
      # distro_codenames (endoflife.date, cached -- see
      # get_distro_codenames) rather than a second maintained list, for
      # the same staleness reason; unrecognized codenames default to
      # Ubuntu, same as before that lookup existed.
      m = re.search(r'([a-zA-Z]+)\d*_(?:i386|amd64|arm64|armhf)\.deb$', name)
      if m:
        codename = m.group(1)
        family = distro_codenames.get(codename.lower(), 'ubuntu')
        info['os'] = family
        info['display_os'] = '%s %s' % (family.capitalize(), codename.capitalize())
        info['short_os'] = codename.capitalize()
        info['os_logo'] = 'squeeze-logo.png' if family == 'debian' else 'ubuntu-logo.png'

      if 'i386' in name:
        info['arch'] = 32
        info['arch_label'] = ARCH_X86_32
      elif is_arm64:
        info['arch'] = 64
        info['arch_label'] = ARCH_ARM64
      elif 'amd64' in name:
        info['arch'] = 64
        info['arch_label'] = ARCH_X86_64
      elif 'armhf' in name:
        info['arch'] = 32
        info['arch_label'] = 'ARM (32-bit)'
        info['display_os'] = 'Raspberry Pi'
        info['short_os'] = 'RPI'
        info['os_logo'] = 'raspberry-pi-logo.png'

    # ARM64/AArch64 is 64-bit but a different CPU family than x86_64,
    # sharing the same (os, arch) pair would otherwise let it collide with.
    # Nothing here can reliably tell an ARM64 visitor from an x86_64 one via
    # User-Agent, so keep ARM64 builds out of find_download()'s auto-picked
    # "best download" matching below (which only ever looks up the plain
    # 'mac'/'fedora'/'windows' os strings) -- defaulting an ARM64 visitor
    # onto an x86_64 binary, or vice versa, is worse than just listing it
    # in the full downloads table for them to pick manually.
    if is_arm64 and info['os'] != 'Unknown':
      info['os'] = info['os'] + '-arm64'

    # Belt-and-suspenders: any asset that still doesn't have a display_os
    # (a genuinely new/unrecognized file type, or a .deb whose name didn't
    # match the codename pattern above) gets a usable fallback instead of
    # silently rendering as a blank entry in the template.
    info.setdefault('display_os', name)
    info.setdefault('short_os', name)
    info.setdefault('os_logo', 'clementine-logo.png')

    # The same system's builds, x86-64 first, then ARM, then 32-bit.
    info['arch_order'] = ARCH_ORDER.get(info.get('arch_label'), len(ARCH_ORDER))

    # Groups the downloads page's tiles by OS family, independent of the
    # ARM64 suffixing above (a 'windows-arm64' tile still belongs in the
    # "Windows" section, not a section of its own).
    family = info['os'][:-len('-arm64')] if info['os'].endswith('-arm64') else info['os']
    info['family'] = family
    info['family_display'] = FAMILY_DISPLAY.get(family, 'Other')

    downloads.append(info)
  return downloads


# What each download's for, under its name: its processors.
ARCH_X86_64 = 'x86-64'
ARCH_ARM64 = 'arm64'
ARCH_X86_32 = 'x86 (32-bit)'
ARCH_ORDER = {ARCH_X86_64: 0, ARCH_ARM64: 1, ARCH_X86_32: 2}


def find_download(downloads, os_name, arch=0):
  # downloads is always every asset of the single most recent release (see
  # _fetch_release_from_github), so there's no separate "is this the latest
  # version" check to make here -- it always is.
  matches = [x for x in downloads if x['os'] == os_name and x['arch'] == arch]
  return copy.deepcopy(matches[0]) if matches else None


# Similar to django.utils.translation.get_language_from_request, which has
# no equivalent in Flask/Jinja2.
def get_language_from_request():
  header = request.headers.get('Accept-Language')
  if not header:
    return None
  accepted_languages = [lang.split(';')[0].replace('-', '_').lower() for lang in header.split(',')]
  lowered = [language.lower() for language in LANGUAGES]
  for accepted_language in accepted_languages:
    if accepted_language in lowered:
      return accepted_language
  return None


def _stylesheet_version():
  # A hash of the stylesheet `make` built, for its URL: /css is cached for a
  # day, so a deploy that changes the CSS would otherwise show the new pages
  # with the old styles until the cache expires.
  try:
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'css', 'all.css'), 'rb') as f:
      return hashlib.sha256(f.read()).hexdigest()[:12]
  except OSError:
    return ''


STYLESHEET_VERSION = _stylesheet_version()


def make_page(template_file, language):
  root_page = '/'
  if language is None:
    language = get_language_from_request()
  else:
    root_page = '/%s/' % language

  if language is None:
    language = 'en'

  translations = get_translations(language)

  downloads = fetch_release()

  # Add datetime objects to the list of news, and translate.
  news = copy.deepcopy(NEWS)
  for n in news:
    n['datetime'] = datetime.datetime.fromtimestamp(n['timestamp'])
    n['title'] = translations.gettext(n['title'])
    n['content'] = translations.gettext(n['content'])

  screenshots = copy.deepcopy(SCREENSHOTS)
  for s in screenshots:
    for e in s['entries']:
      e['title_en'] = e['title']
      e['title'] = translations.gettext(e['title'])
      # These have long been served from the old pages repository.
      e['thumbnail'] = 'https://clementine-player.github.io/pages/images/thumbnails/' + e['file']
      e['full'] = 'https://clementine-player.github.io/pages/images/screenshots/' + e['file']

  android_screenshots = None
  release_screenshots = None
  if template_file in ('main.html', 'screenshots.html'):
    android_screenshots = fetch_android_screenshots()
    release_screenshots = fetch_release_screenshots()

  platform_names = dict(RELEASE_PLATFORMS)
  platforms = visitor_platforms(request.headers.get('User-Agent', ''))

  def release_entry(platform, screen):
    shot = release_screenshots['platforms'].get(platform, {}).get(screen)
    if shot is None:
      return None
    title = dict(RELEASE_SCREENSHOTS)[screen]
    values = {'platform': platform_names.get(platform, platform)}
    try:
      return dict(shot, title=translations.gettext(title) % values)
    except (KeyError, TypeError, ValueError):
      # A translation that lost its %(platform)s.
      return dict(shot, title=title % values)

  release_group = None
  desktop = None
  if release_screenshots:
    entries = [release_entry(p, screen) for p in platforms for screen, _title in RELEASE_SCREENSHOTS]
    release_group = {
      'version': release_screenshots['version'],
      'entries': [e for e in entries if e],
    }
    # The home page's two: the library, light and dark, on the visitor's
    # platform if the release has them, else the next one that does.
    for p in platforms:
      pair = [release_entry(p, 'library'), release_entry(p, 'library-dark')]
      if all(pair):
        desktop = pair
        break

  # The home page: two of Clementine, then two of Clementine Remote. Without
  # them from the releases, the old ones.
  old = screenshots[0]['entries']
  old_desktop = [e for e in old if 'Android' not in e['title_en']][:2]
  old_android = [e for e in old if 'Android' in e['title_en']]
  android_entries = None
  if android_screenshots:
    by_number = {e['number']: e for e in android_screenshots['entries']}
    android_entries = [dict(by_number[n], title=translations.gettext(title), phone=True)
                       for n, title in ANDROID_HOME_SCREENSHOTS if n in by_number]
    if len(android_entries) != len(ANDROID_HOME_SCREENSHOTS):
      android_entries = None
  latest_screenshots = (desktop or old_desktop) + (android_entries or old_android)

  # Try to detect the user's OS and architecture.
  ua = request.headers.get('User-Agent', '').lower()
  if 'win' in ua:
    best_download = find_download(downloads, 'windows', 64)
  elif 'mac' in ua:
    best_download = find_download(downloads, 'mac', 64)
  elif 'fedora' in ua:
    best_download = find_download(downloads, 'fedora', 64 if '64' in ua else 32)
  else:
    best_download = None

  languages = [{'code': x, 'name': LANGUAGE_NAMES[x], 'current': x == language} for x in LANGUAGES]

  params = {
    '_': make_translator(translations),
    'best_download':      best_download,
    'downloads':          downloads,
    # downloads is always every asset of the single most recent release, so
    # it's already "latest" in full -- no separate version to filter by.
    'latest_downloads':   downloads,
    'latest_screenshots': latest_screenshots,
    'latest_version':     downloads[0]['ver'] if downloads else None,
    'news':               news,
    'language':           language,
    'languages':          languages,
    'root_page':          root_page,
    'screenshots':        screenshots,
    'android_screenshots': android_screenshots,
    'release_screenshots': release_group,
    'is_rtl':             language in ('ar', 'fa', 'he'),
    'stylesheet_version': STYLESHEET_VERSION,
  }

  rendered = app.jinja_env.get_template(template_file).render(params)
  response = Response(rendered)
  response.headers['Content-Language'] = language
  return response


@app.route('/')
@app.route('/<lang:language>/')
def index(language=None):
  return make_page('main.html', language)


@app.route('/about')
@app.route('/<lang:language>/about')
def about(language=None):
  return make_page('main.html', language)


@app.route('/screenshots')
@app.route('/<lang:language>/screenshots')
def screenshots_page(language=None):
  return make_page('screenshots.html', language)


@app.route('/downloads')
@app.route('/<lang:language>/downloads')
def downloads_page(language=None):
  return make_page('downloads.html', language)


@app.route('/participate')
@app.route('/<lang:language>/participate')
def participate(language=None):
  return make_page('participate.html', language)


@app.route('/privacy')
@app.route('/<lang:language>/privacy')
def privacy(language=None):
  return make_page('privacy.html', language)


@app.route('/wiimote')
def wiimote():
  return redirect('https://github.com/clementine-player/Clementine/wiki/Wii-Remotes')


@app.route('/.well-known/acme-challenge/<path:_unused>', methods=['GET', 'POST'])
def acme_challenge(_unused):
  return redirect('https://builds.clementine-player.org' + request.path)
