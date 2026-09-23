# -*- coding: utf-8 -*-

import base64
import copy
import datetime
import json
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
from data import NEWS
from data import SCREENSHOTS

from thumbnailer import thumbnailer

RELEASES_KEY = 'github_releases'
RELEASES_CACHE_SECONDS = 60 * 60
LOCAL_CACHE_SECONDS = 60

# Section headings for the downloads page, keyed by the base os string
# (before any '-arm64' suffix).
FAMILY_DISPLAY = {
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
  # (e.g. participate.html's "...stickers on %(unixstickers)s.").
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


def fetch_release():
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

  result = json.loads(content)
  downloads = []
  for asset in result['assets']:
    name = asset['name']
    name_lower = name.lower()
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
      if is_arm64 or 'x86_64' in name:
        info['arch'] = 64
      elif 'i686' in name:
        info['arch'] = 32
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
      else:
        info['arch'] = 64
    elif name_lower.endswith('.deb'):
      # Extract the distro codename directly from the filename instead of
      # checking it against a maintained list of known Ubuntu/Debian
      # release names -- that list needs a new entry roughly every 6
      # months (Ubuntu) or 2 years (Debian) and reliably goes stale (see
      # the Fedora/Ubuntu-codename bug this replaced). Package filenames
      # for multi-distro builds conventionally embed the codename as a
      # word immediately before the architecture suffix, e.g.
      # "clementine_1.3.9-jammy1_amd64.deb" -- capture that directly.
      # Can't reliably tell Debian from Ubuntu this way (both just embed
      # a bare codename), so this no longer distinguishes them -- every
      # .deb gets the same generic branding, with the actual codename
      # (immediately recognizable to anyone running that distro) as the
      # label.
      m = re.search(r'([a-zA-Z]+)\d*_(?:i386|amd64|arm64|armhf)\.deb$', name)
      if m:
        codename = m.group(1).capitalize()
        info['os'] = 'ubuntu'
        info['display_os'] = codename
        info['short_os'] = codename
        info['os_logo'] = 'ubuntu-logo.png'

      if 'i386' in name:
        info['arch'] = 32
      elif 'amd64' in name or is_arm64:
        info['arch'] = 64
      elif 'armhf' in name:
        info['arch'] = 32
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
      info['display_os'] = info.get('display_os', name) + ' (ARM64)'
      info['short_os'] = (info.get('short_os', name) + ' ARM64').strip()

    # Belt-and-suspenders: any asset that still doesn't have a display_os
    # (a genuinely new/unrecognized file type, or a .deb whose name didn't
    # match the codename pattern above) gets a usable fallback instead of
    # silently rendering as a blank entry in the template.
    info.setdefault('display_os', name)
    info.setdefault('short_os', name)
    info.setdefault('os_logo', 'clementine-logo.png')

    # Groups the downloads page's tiles by OS family, independent of the
    # ARM64 suffixing above (a 'windows-arm64' tile still belongs in the
    # "Windows" section, not a section of its own).
    family = info['os'][:-len('-arm64')] if info['os'].endswith('-arm64') else info['os']
    info['family'] = family
    info['family_display'] = FAMILY_DISPLAY.get(family, 'Other')

    downloads.append(info)
  return downloads


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
      e['title'] = translations.gettext(e['title'])

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
    'latest_screenshots': screenshots[0]['entries'],
    'latest_version':     downloads[0]['ver'] if downloads else None,
    'news':               news,
    'language':           language,
    'languages':          languages,
    'root_page':          root_page,
    'screenshots':        screenshots,
    'is_rtl':             language in ('ar', 'fa', 'he'),
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
