# -*- coding: utf-8 -*-
"""Boots the Flask app for real and fires requests through every route, to
catch import-time crashes and route-level regressions before they reach a
real deploy. Run from the www.clementine-player.org directory, after `make`:

    GITHUB_TOKEN=x PYTHONPATH=tests/fakes python3 tests/smoke_test.py

PYTHONPATH=tests/fakes shadows google.cloud.datastore with an in-memory fake
(see tests/fakes/google/cloud/datastore.py) so this doesn't need real GCP
credentials. Setting GITHUB_TOKEN avoids main.py's Secret Manager fallback,
which would need credentials too.
"""
import functools
import http.server
import json
import os
import sys
import threading
import traceback

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP_DIR)

import main  # noqa: E402

# Avoid a real network call to GitHub: return a small canned release.
CANNED_RELEASE = json.dumps({
    'tag_name': '1.4.0',
    'assets': [
        {
            'browser_download_url': 'https://example.com/clementine-ubuntu.deb',
            'content_type': 'application/vnd.debian.binary-package',
            'name': 'clementine_1.4.0-jammy1_amd64.deb',
        },
        {
            'browser_download_url': 'https://example.com/clementine-debian.deb',
            'content_type': 'application/vnd.debian.binary-package',
            'name': 'clementine_1.4.0-bookworm1_amd64.deb',
        },
        {
            'browser_download_url': 'https://example.com/clementine.dmg',
            'content_type': 'application/x-apple-diskimage',
            'name': 'clementine-1.4.0.dmg',
        },
        {
            'browser_download_url': 'https://example.com/clementine.exe',
            'content_type': 'application/x-ms-dos-executable',
            'name': 'ClementineSetup-1.4.0.exe',
        },
        {
            'browser_download_url': 'https://example.com/clementine.rpm',
            'content_type': 'application/x-rpm',
            'name': 'clementine-1.4.0-1.fc39.x86_64.rpm',
        },
        {
            'browser_download_url': 'https://example.com/clementine-debuginfo.rpm',
            'content_type': 'application/x-rpm',
            'name': 'clementine-debuginfo-1.4.0-1.fc39.x86_64.rpm',
        },
        {
            'browser_download_url': 'https://example.com/clementine-debugsource.rpm',
            'content_type': 'application/x-rpm',
            'name': 'clementine-debugsource-1.4.0-1.fc39.x86_64.rpm',
        },
    ],
})
main._fetch_release_from_github = lambda: CANNED_RELEASE

# Avoid a real network call to endoflife.date: return a small canned
# codename->family mapping covering both branches.
main.get_distro_codenames = lambda: {'jammy': 'ubuntu', 'bookworm': 'debian'}

# Avoid real network calls for Clementine Remote's screenshots too: the newest
# release, with three of them.
main._fetch_android_screenshots_from_github = lambda: json.dumps(
    {'tag': 'v13.3', 'numbers': [1, 2, 3]})

print('import main: OK, app = %r' % (main.app,))

downloads = main.fetch_release()
downloads_by_os = {d['os']: d for d in downloads}
assert downloads_by_os['ubuntu']['display_os'] == 'Ubuntu Jammy', downloads_by_os['ubuntu']
assert downloads_by_os['debian']['display_os'] == 'Debian Bookworm', downloads_by_os['debian']
print('Debian/Ubuntu split by distro_codenames: OK')

fedora_downloads = [d for d in downloads if d['os'] == 'fedora']
assert len(fedora_downloads) == 1, fedora_downloads  # debuginfo/debugsource omitted
print('Fedora debuginfo/debugsource rpms omitted: OK')

client = main.app.test_client()

routes = [
    ('/', 200), ('/en/', 200), ('/fr/about', 200), ('/downloads', 200),
    ('/pt_BR/downloads', 200), ('/screenshots', 200), ('/participate', 200),
    ('/privacy', 200), ('/de/privacy', 200), ('/wiimote', 302),
    ('/.well-known/acme-challenge/xyz', 302),
    ('/xyz123/about', 404),  # malformed language code should 404, not crash
]

failures = []

# The screenshots page shows Clementine Remote's, and leaves them out rather
# than failing when they can't be fetched.
page = client.get('/screenshots').get_data(as_text=True)
for expected in ('Clementine Remote for Android 13.3',
                 '/thumbnails/android/v13.3/3.png',
                 'https://raw.githubusercontent.com/clementine-player/Android-Remote/v13.3/'):
  if expected not in page:
    failures.append(('/screenshots', 'missing %r' % expected, 'present'))
# The home page shows its player and library in place of the old app's.
home = client.get('/').get_data(as_text=True)
for expected in ('/thumbnails/android/v13.3/1.png', '/thumbnails/android/v13.3/2.png',
                 'Browsing the library from the Android app', 'clementine-1.2-1.png'):
  if expected not in home:
    failures.append(('/', 'missing %r' % expected, 'present'))
if 'clementine-1.2-3.png' in home:
  failures.append(('/', 'still shows the old app', 'replaced'))

fetch = main._fetch_android_screenshots_from_github
attempts = []
def unavailable():
  attempts.append(1)
  raise main.GithubFetchError('GitHub is down')
main._fetch_android_screenshots_from_github = unavailable
main._local_cache.clear()
from google.cloud import datastore as fake_datastore  # tests/fakes
fake_datastore._STORE.clear()
resp = client.get('/screenshots')
if resp.status_code != 200:
  failures.append(('/screenshots without Android', resp.status_code, 200))
# The home page falls back to the old screenshots, and doesn't ask GitHub
# again straight away.
main._local_cache.clear()
home = client.get('/').get_data(as_text=True)
if 'clementine-1.2-3.png' not in home:
  failures.append(('/ without Android', 'no old screenshots', 'old screenshots'))
if len(attempts) != 1:
  failures.append(('/ without Android', '%d fetches' % len(attempts), '1 fetch'))
main._fetch_android_screenshots_from_github = fetch
fake_datastore._STORE.clear()
main._local_cache.clear()
print('Clementine Remote screenshots on /screenshots: %s' % ('OK' if not failures else 'FAILED'))

# Its thumbnails only ever come from Android-Remote's release tags.
routes += [
    ('/thumbnails/android/evil/1.png', 404),
    ('/thumbnails/android/v13.3/9.png', 404),
    ('/thumbnails/android/v13.3/0.png', 404),
]

for path, expected in routes:
  try:
    resp = client.get(path, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    ok = resp.status_code == expected
    print('%-35s -> %s (expected %s)%s' % (path, resp.status_code, expected, '' if ok else '  <== MISMATCH'))
    if not ok:
      failures.append((path, resp.status_code, expected))
  except Exception:
    print('%-35s -> EXCEPTION' % path)
    traceback.print_exc()
    failures.append((path, 'exception', expected))

# Exercise the thumbnailer route against a real screenshot file. It fetches
# the "original" image over HTTP from its own host, so serve one from a
# throwaway local HTTP server rather than test_client() (which has no real
# socket for that inner request to hit).
screenshots_dir = os.path.join(APP_DIR, 'static', 'screenshots')
static_dir = os.path.join(APP_DIR, 'static')
sample_files = [f for f in os.listdir(screenshots_dir) if f.endswith('.png')] if os.path.isdir(screenshots_dir) else []
if sample_files:
  sample = sample_files[0]
  handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=static_dir)
  httpd = http.server.HTTPServer(('127.0.0.1', 8091), handler)
  thread = threading.Thread(target=httpd.serve_forever, daemon=True)
  thread.start()
  try:
    resp = client.get('/thumbnails/' + sample, base_url='http://127.0.0.1:8091')
    print('%-35s -> %s (%d bytes)' % ('/thumbnails/' + sample, resp.status_code, len(resp.data)))
    if resp.status_code != 200:
      failures.append(('/thumbnails/' + sample, resp.status_code, 200))
  except Exception:
    traceback.print_exc()
    failures.append(('/thumbnails/' + sample, 'exception', 200))
  finally:
    httpd.shutdown()
else:
  print('No sample screenshot found, skipping thumbnailer test')

if failures:
  print('\nFAILURES: %r' % (failures,))
  sys.exit(1)
else:
  print('\nAll routes OK.')
