# -*- coding: utf-8 -*-

import datetime
import json
import logging
import os
import time
from email.utils import format_datetime
from operator import itemgetter
from urllib.parse import urlencode

import requests
from flask import Flask, Response, abort, redirect, request
from google.cloud import ndb
from google.cloud import tasks_v2

import models

GAE_PROJECT = os.environ.get('GOOGLE_CLOUD_PROJECT', 'clementine-data')
# The clementine-data App Engine app's region -- Cloud Tasks queues must be
# created in the same region. Confirm with:
#   gcloud app describe --project=clementine-data --format='value(locationId)'
TASKS_LOCATION = os.environ.get('TASKS_LOCATION', 'us-central')

# Served from a Cloudflare R2 bucket on the cloud.clementine-player.org
# custom domain (R2 has no egress charges).
RAINYMOOD_URL = 'https://cloud.clementine-player.org/RainyMood.mp3'
ICECAST_URL = 'http://dir.xiph.org/yp.xml'
GITHUB_RELEASES = 'https://api.github.com/repos/clementine-player/Clementine/releases'

BIO_URL = 'https://bio-5ctfinxp4a-lz.a.run.app/'
IMAGES_URL = 'https://images-5ctfinxp4a-lz.a.run.app/'

VERSIONS_CACHE_KEY = 'sparkle-versions-%s'
VERSIONS_CACHE_SECONDS = 60 * 10
BIO_CACHE_KEY = 'bio/%s/%s'
# Bumped from 'images/%s' when the images backend moved off Spotify, so
# error responses cached before caching was limited to successes are skipped.
IMAGES_CACHE_KEY = 'images-v2/%s'
FETCH_CACHE_SECONDS = 60 * 60 * 24

LOCAL_CACHE_SECONDS = 60

app = Flask(__name__, template_folder='.')
# Django (the original template engine here) renders a None value as empty
# string; Jinja2 renders it as the literal text "None". Several optional
# Version fields (revision, signature, bundle_size, changelog_link) are
# genuinely unset for some real entities, so without this the Sparkle feeds
# would start emitting literal "None" into XML attributes that used to be
# empty.
app.jinja_env.finalize = lambda value: '' if value is None else value

ndb_client = ndb.Client(project=GAE_PROJECT)
tasks_client = tasks_v2.CloudTasksClient()


@app.before_request
def _open_ndb_context():
  ctx = ndb_client.context()
  ctx.__enter__()
  request.environ['_ndb_context'] = ctx


@app.teardown_request
def _close_ndb_context(exc):
  ctx = request.environ.get('_ndb_context')
  if ctx is not None:
    ctx.__exit__(None, None, None)


def _enqueue_task(relative_uri, queue='default', params=None):
  # Cloud Tasks replacement for taskqueue.add(url=..., params=...). Never
  # let a failure to enqueue break the request that triggered it -- the
  # original code caught and logged taskqueue.Error the same way.
  try:
    parent = tasks_client.queue_path(GAE_PROJECT, TASKS_LOCATION, queue)
    task = {
        'app_engine_http_request': {
            'http_method': tasks_v2.HttpMethod.POST,
            'relative_uri': relative_uri,
            'headers': {'Content-Type': 'application/x-www-form-urlencoded'},
            'body': urlencode(params or {}).encode('utf-8'),
        }
    }
    # Without explicit routing, Cloud Tasks delivers to whichever version is
    # serving default traffic, not the one that enqueued the task (which is
    # what the old taskqueue API did). Pin it, so an unpromoted version runs
    # its own task handlers and mixed-version rollouts don't cross-deliver.
    if os.environ.get('GAE_VERSION'):
      task['app_engine_http_request']['app_engine_routing'] = {
          'service': os.environ.get('GAE_SERVICE', 'default'),
          'version': os.environ['GAE_VERSION'],
      }
    tasks_client.create_task(parent=parent, task=task)
  except Exception:
    logging.exception('Failed to enqueue task %s', relative_uri)


def _require_cron():
  if request.headers.get('X-Appengine-Cron') != 'true':
    abort(403)


def _require_task_queue():
  if not request.headers.get('X-AppEngine-QueueName'):
    abort(403)


def rfc2822(value):
  if isinstance(value, str):
    value = datetime.datetime.fromisoformat(value)
  return format_datetime(value)


app.jinja_env.filters['rfc2822'] = rfc2822


# ---------------------------------------------------------------------------
# Datastore-backed cache, replacing memcache. A cold-start cache miss here
# should never fall straight through to a rate-limited/billed backend (the
# Cloud Run bio/images services) or force a Datastore query every request
# (the Sparkle version list) -- this persists across restarts and is shared
# across instances, with an in-process layer in front for same-instance
# speed. Mirrors www.clementine-player.org/main.py's identical cache.

class Cache(ndb.Model):
  value = ndb.TextProperty()
  fetched_at = ndb.FloatProperty()


_local_cache = {}


def _read_cache(key):
  local = _local_cache.get(key)
  if local is not None and time.time() - local[2] < LOCAL_CACHE_SECONDS:
    return {'value': local[0], 'fetched_at': local[1]}

  entity = Cache.get_by_id(key)
  if entity is None:
    return None
  _local_cache[key] = (entity.value, entity.fetched_at, time.time())
  return {'value': entity.value, 'fetched_at': entity.fetched_at}


def _write_cache(key, value, fetched_at):
  Cache(id=key, value=value, fetched_at=fetched_at).put()
  _local_cache[key] = (value, fetched_at, time.time())


# ---------------------------------------------------------------------------
# Sparkle / WinSparkle update feeds.

def _version_to_dict(v):
  return {
      'platform': v.platform,
      'revision': v.revision,
      'version': v.version,
      'download_link': v.download_link,
      'signature': v.signature,
      'bundle_size': v.bundle_size,
      'changelog_link': v.changelog_link,
      'changelog': v.changelog,
      'publish_date': v.publish_date.isoformat() if v.publish_date else None,
      'min_version': v.min_version,
  }


def _fetch_versions(platform):
  now = time.time()
  cache_key = VERSIONS_CACHE_KEY % platform
  cached = _read_cache(cache_key)
  if cached is not None and now - cached['fetched_at'] < VERSIONS_CACHE_SECONDS:
    return json.loads(cached['value'])

  versions = [
      _version_to_dict(v)
      for v in models.Version.query(models.Version.platform == platform).fetch(20)
  ]
  _write_cache(cache_key, json.dumps(versions), now)
  return versions


def _write_sparkle_response(template_name, platform):
  versions = _fetch_versions(platform)
  rendered = app.jinja_env.get_template(template_name).render(versions=versions)

  useragent = request.headers.get('User-Agent', '')
  if useragent:
    clementine = useragent.split(' ')[0]
    _enqueue_task('/_tasks/counters', params={'key': clementine})

  return Response(rendered, mimetype='text/xml')


@app.route('/sparkle')
def sparkle():
  return _write_sparkle_response('sparkle.xml', 'mac')


@app.route('/sparkle-windows')
def sparkle_windows():
  return _write_sparkle_response('winsparkle.xml', 'windows')


@app.route('/versions', methods=['GET', 'POST'])
def versions():
  # Publishing new Sparkle versions through this page isn't used anymore --
  # stubbed out rather than ported, since login:admin (what gated it before)
  # has no gen2 equivalent and there's nothing here worth protecting instead.
  # New Version entities can still be added directly via the Datastore
  # console if ever needed; /sparkle and /sparkle-windows keep reading
  # whatever's there.
  return Response('This page is no longer available.', status=410)


# ---------------------------------------------------------------------------
# Misc redirects.

@app.route('/rainymood')
def rainymood():
  _enqueue_task('/_tasks/counters', params={'key': 'rain'})
  return redirect(RAINYMOOD_URL)


@app.route('/icecast-directory')
def icecast_directory():
  _enqueue_task('/_tasks/counters', params={'key': 'icecast-directory'})
  return redirect(ICECAST_URL)


@app.route('/geolocate')
def geolocate():
  headers = request.headers
  if ('X-Appengine-City' in headers and 'X-Appengine-Citylatlong' in headers
      and 'X-Appengine-Country' in headers):
    return {
        'city': headers['X-Appengine-City'],
        'latlng': headers['X-Appengine-Citylatlong'],
        'country': headers['X-Appengine-Country'],
    }
  abort(404)


@app.route('/downloadcount')
def downloadcount():
  result = requests.get(GITHUB_RELEASES)
  if result.status_code >= 400:
    return 'Could not fetch release information from Github', 500

  releases = []
  for release in result.json():
    files = [{'name': x['name'], 'count': x['download_count']} for x in release['assets']]
    total = sum(x['count'] for x in files)
    files.append({
        'name': 'Linux total',
        'count': sum(x['count'] for x in files if x['name'].endswith(('.deb', '.rpm'))),
    })
    files.sort(key=itemgetter('count'), reverse=True)
    releases.append({'name': release['name'], 'files': files, 'total': total})

  rendered = app.jinja_env.get_template('downloads.html').render(releases=releases)
  return Response(rendered)


@app.route('/.well-known/acme-challenge/<path:_>', methods=['GET', 'POST'])
def acme_challenge(_):
  return redirect('https://builds.clementine-player.org' + request.path)


@app.route('/oauth')
@app.route('/skydrive')  # Legacy support
def oauth():
  port = request.args.get('port')
  if not port:
    # SoundCloud forces us to have a fixed URL (i.e. without the port
    # parameter). However, we can have a 'state' param, which will be
    # appended to the redirect URI.
    port = request.args.get('state')
  code = request.args.get('code')
  return redirect('http://localhost:%s/?code=%s' % (port, code))


def _proxy_cached(cache_key, url, params):
  now = time.time()
  cached = _read_cache(cache_key)
  if cached is not None and now - cached['fetched_at'] < FETCH_CACHE_SECONDS:
    return Response(cached['value'], mimetype='application/json; charset=utf-8')
  try:
    response = requests.get(url, params=params, timeout=30)
  except requests.RequestException as e:
    logging.warning('Fetching %s failed: %s', url, e)
    return Response('Upstream request failed', status=502)
  # Only cache successes, so a transient backend error (or a not-found) isn't
  # served back for the next day as if it were a real answer.
  if response.status_code == 200:
    _write_cache(cache_key, response.text, now)
  return Response(response.text, status=response.status_code,
                  mimetype='application/json; charset=utf-8')


@app.route('/fetchbio')
def fetchbio():
  artist = request.args.get('artist', '')
  lang = request.args.get('lang', '')
  return _proxy_cached(BIO_CACHE_KEY % (artist, lang), BIO_URL,
                       {'artist': artist, 'lang': lang})


@app.route('/fetchimages')
def fetchimages():
  artist = request.args.get('artist', '')
  return _proxy_cached(IMAGES_CACHE_KEY % artist, IMAGES_URL, {'artist': artist})


@app.route('/')
def index():
  return redirect('http://www.clementine-player.org/')


# ---------------------------------------------------------------------------
# Task/cron handlers.

@app.route('/_tasks/counters', methods=['POST'])
def tasks_counters():
  _require_task_queue()
  key = request.form.get('key')

  def transaction():
    counter = models.Counter.get_by_id(key)
    if counter is None:
      counter = models.Counter(id=key, count=1)
    else:
      counter.count += 1
    counter.put()

  ndb.transaction(transaction)
  return 'OK'


@app.route('/_tasks/snapshot', methods=['GET'])
def tasks_snapshot_cron():
  _require_cron()
  _enqueue_task('/_tasks/snapshot')
  return 'OK'


@app.route('/_tasks/snapshot', methods=['POST'])
def tasks_snapshot_run():
  _require_task_queue()
  counters = models.Counter.query().fetch(10)
  for counter in counters:
    models.CounterSnapshot(counter=counter.key, count=counter.count).put()
  return 'OK'

