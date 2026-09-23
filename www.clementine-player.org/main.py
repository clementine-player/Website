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

from data import DEBIAN_NAMES
from data import LANGUAGE_NAMES
from data import LANGUAGES
from data import LATEST_VERSION
from data import NEWS
from data import SCREENSHOTS
from data import UBUNTU_NAMES

from thumbnailer import thumbnailer

RELEASES_KEY = 'github_releases'
RELEASES_CACHE_SECONDS = 60 * 60
LOCAL_CACHE_SECONDS = 60


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
  entity = datastore.Entity(client.key('Cache', key))
  entity.update({'value': value, 'fetched_at': fetched_at})
  client.put(entity)
  _local_cache[key] = (value, fetched_at, time.time())


def _fetch_release_from_github():
  token = base64.b64encode(('%s:' % GITHUB_TOKEN).encode('utf-8')).decode('ascii')
  r = requests.get(
      'https://api.github.com/repos/clementine-player/Clementine/releases/latest',
      headers={'Authorization': 'Basic %s' % token})
  if r.status_code != 200:
    raise GithubFetchError('Error fetching releases: %d %s' % (r.status_code, r.text))
  return r.text


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
    info = {
      'os': 'Unknown',
      'ver': result['tag_name'],
      'arch': 0,
      'url': asset['browser_download_url'],
    }
    if asset['content_type'] == 'application/x-rpm':
      info['os'] = 'fedora'
      info['short_os'] = 'Fedora'
      info['os_logo'] = 'fedora-logo.png'
      if 'x86_64' in asset['name']:
        info['arch'] = 64
      elif 'i686' in asset['name']:
        info['arch'] = 32
      m = re.search(r'\.fc(\d+)\.', asset['name'])
      if m:
        info['display_os'] = 'Fedora %s' % m.group(1)
      else:
        info['display_os'] = 'Fedora'
    elif asset['content_type'] == 'application/x-apple-diskimage':
      info['os'] = 'mac'
      info['display_os'] = 'Mac'
      info['short_os'] = 'Mac'
      info['os_logo'] = 'leopard-logo.png'
      info['arch'] = 64
    elif asset['content_type'] == 'application/x-xz':
      info['os'] = 'source'
      info['display_os'] = 'Source Code'
      info['short_os'] = 'Source'
      info['os_logo'] = 'source-logo.png'
    elif asset['content_type'] == 'application/x-ms-dos-executable':
      info['os'] = 'windows'
      info['display_os'] = 'Windows'
      info['short_os'] = 'Windows'
      info['os_logo'] = 'windows-logo.png'
      info['arch'] = 32
    elif asset['content_type'] in ('application/x-deb', 'application/vnd.debian.binary-package'):
      for n in DEBIAN_NAMES:
        if n in asset['name']:
          info['os'] = 'debian'
          info['display_os'] = 'Debian %s' % n.capitalize()
          info['short_os'] = n.capitalize()
          info['os_logo'] = 'squeeze-logo.png'

      for n in UBUNTU_NAMES:
        if n in asset['name']:
          info['os'] = 'ubuntu'
          info['display_os'] = 'Ubuntu %s' % n.capitalize()
          info['short_os'] = n.capitalize()
          info['os_logo'] = 'ubuntu-logo.png'

      if 'i386' in asset['name']:
        info['arch'] = 32
      elif 'amd64' in asset['name']:
        info['arch'] = 64
      elif 'armhf' in asset['name']:
        info['arch'] = 32
        info['display_os'] = 'Raspberry Pi'
        info['short_os'] = 'RPI'
        info['os_logo'] = 'raspberry-pi-logo.png'

    downloads.append(info)
  return downloads


def find_download(downloads, os_name, arch=0):
  matches = [x for x in downloads if x['os'] == os_name
                                  and x['arch'] == arch
                                  and x['ver'][:3] == LATEST_VERSION[:3]]
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
    best_download = find_download(downloads, 'windows', 32)
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
    'latest_downloads':   [x for x in downloads if x['ver'] == LATEST_VERSION],
    'latest_screenshots': screenshots[0]['entries'],
    'latest_version':     LATEST_VERSION,
    'news':               news,
    'language':           language,
    'languages':          languages,
    'old_downloads':      [x for x in downloads if x['ver'] != LATEST_VERSION],
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
