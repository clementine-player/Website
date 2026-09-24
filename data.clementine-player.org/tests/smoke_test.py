# -*- coding: utf-8 -*-
"""Boots the Flask app for real and fires requests through every route, to
catch import-time crashes and route-level regressions before they reach a
real deploy. Run from the data.clementine-player.org directory:

    PYTHONPATH=tests/fakes python3 tests/smoke_test.py

PYTHONPATH=tests/fakes shadows google.cloud.ndb and google.cloud.tasks_v2
with in-memory fakes (see tests/fakes/google/cloud/) so this doesn't need
real GCP credentials or network access.
"""
import os
import sys
import traceback
from unittest import mock

os.environ.setdefault('GOOGLE_CLOUD_PROJECT', 'fake-project')

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP_DIR)

import main  # noqa: E402
import models  # noqa: E402

print('import main: OK, app = %r' % (main.app,))

failures = []


def check(label, condition):
  print('%-55s -> %s' % (label, 'OK' if condition else 'FAILED'))
  if not condition:
    failures.append(label)


client = main.app.test_client()

# Seed some Version entities the way the (now-stubbed) /versions POST used
# to, directly through the model, to exercise /sparkle and /sparkle-windows
# against real data.
with main.ndb_client.context():
  models.Version(
      platform='mac', revision='r1', version='1.4.1',
      download_link='https://example.com/clementine.dmg',
      signature='c2lnbmF0dXJl', bundle_size=123456,
      changelog_link='https://example.com/changelog', min_version='10.14',
  ).put()
  models.Version(
      platform='windows', revision='r1', version='1.4.1',
      download_link='https://example.com/ClementineSetup.exe',
  ).put()

resp = client.get('/sparkle')
check('/sparkle -> 200', resp.status_code == 200)
check('/sparkle contains version', b'1.4.1' in resp.data)
check('/sparkle contains minimumSystemVersion', b'10.14' in resp.data)
check('/sparkle has a real RFC 2822 pubDate (not a crash)',
      b'pubDate' in resp.data and b'-0000' in resp.data)

resp = client.get('/sparkle-windows')
check('/sparkle-windows -> 200', resp.status_code == 200)
check('/sparkle-windows contains version', b'1.4.1' in resp.data)

resp = client.get('/versions')
check('/versions stub -> 410 Gone', resp.status_code == 410)

resp = client.get('/')
check('/ -> 302 redirect to www', resp.status_code == 302
      and resp.headers['Location'] == 'http://www.clementine-player.org/')

resp = client.get('/.well-known/acme-challenge/xyz')
check('/.well-known/acme-challenge GET -> 302 to builds.', resp.status_code == 302
      and resp.headers['Location'] == 'https://builds.clementine-player.org/.well-known/acme-challenge/xyz')

resp = client.post('/.well-known/acme-challenge/xyz')
check('/.well-known/acme-challenge POST -> 302 to builds.', resp.status_code == 302)

resp = client.get('/oauth?port=1234&code=abcd')
check('/oauth -> redirect with code', resp.status_code == 302
      and resp.headers['Location'] == 'http://localhost:1234/?code=abcd')

resp = client.get('/skydrive?state=5678&code=efgh')
check('/skydrive (legacy) -> redirect using state as port', resp.status_code == 302
      and resp.headers['Location'] == 'http://localhost:5678/?code=efgh')

resp = client.get('/geolocate')
check('/geolocate without headers -> 404', resp.status_code == 404)

resp = client.get('/geolocate', headers={
    'X-Appengine-City': 'Mountain View',
    'X-Appengine-Citylatlong': '37.386,-122.084',
    'X-Appengine-Country': 'US',
})
check('/geolocate with headers -> 200 JSON', resp.status_code == 200
      and resp.get_json()['city'] == 'Mountain View')

with mock.patch.object(main.requests, 'get') as mock_get:
  mock_get.return_value.status_code = 200
  mock_get.return_value.json.return_value = [
      {'name': 'Clementine 1.4.1', 'assets': [
          {'name': 'clementine.deb', 'download_count': 10},
          {'name': 'clementine.rpm', 'download_count': 5},
          {'name': 'clementine.exe', 'download_count': 20},
      ]},
  ]
  resp = client.get('/downloadcount')
  check('/downloadcount -> 200', resp.status_code == 200)
  check('/downloadcount includes Linux total', b'Linux total' in resp.data)

with mock.patch.object(main.requests, 'get') as mock_get:
  mock_get.return_value.text = '{"bio": "hello"}'
  resp = client.get('/fetchbio?artist=X&lang=en')
  check('/fetchbio -> 200 proxied', resp.status_code == 200 and b'hello' in resp.data)
  check('/fetchbio calls the bio backend once', mock_get.call_count == 1)
  resp2 = client.get('/fetchbio?artist=X&lang=en')
  check('/fetchbio second request served from cache (no extra call)', mock_get.call_count == 1)
  check('/fetchbio cached response still correct', b'hello' in resp2.data)

with mock.patch.object(main.requests, 'get') as mock_get:
  mock_get.return_value.text = '{"images": []}'
  resp = client.get('/fetchimages?artist=X')
  check('/fetchimages -> 200 proxied', resp.status_code == 200)

with mock.patch.object(main.requests, 'get') as mock_get:
  mock_get.return_value.status_code = 200
  resp = client.get('/rainymood')
  check('/rainymood -> 302 redirect', resp.status_code == 302)

resp = client.get('/icecast-directory')
check('/icecast-directory -> 302 redirect to xiph', resp.status_code == 302
      and resp.headers['Location'] == main.ICECAST_URL)

# Task/cron endpoints: rejected without the App-Engine-only headers that
# prove the request came from Cloud Tasks/Cron, not the public internet
# (the gen2 replacement for login:admin on these routes).
resp = client.post('/_tasks/counters', data={'key': 'Clementine'})
check('/_tasks/counters without queue header -> 403', resp.status_code == 403)

resp = client.post('/_tasks/counters', data={'key': 'Clementine'},
                    headers={'X-AppEngine-QueueName': 'default'})
check('/_tasks/counters with queue header -> 200', resp.status_code == 200)
with main.ndb_client.context():
  counter = models.Counter.get_by_id('Clementine')
  check('/_tasks/counters incremented the counter', counter is not None and counter.count == 1)

resp = client.get('/_tasks/snapshot')
check('/_tasks/snapshot GET without cron header -> 403', resp.status_code == 403)

resp = client.get('/_tasks/snapshot', headers={'X-Appengine-Cron': 'true'})
check('/_tasks/snapshot GET with cron header -> 200 (enqueues)', resp.status_code == 200)
check('snapshot cron enqueued a task', any(
    t['task']['app_engine_http_request']['relative_uri'] == '/_tasks/snapshot'
    for t in main.tasks_v2.TASKS))

os.environ['GAE_VERSION'] = 'test-version'
client.get('/icecast-directory')
del os.environ['GAE_VERSION']
check('tasks are routed back to the version that enqueued them',
      main.tasks_v2.TASKS[-1]['task']['app_engine_http_request'].get('app_engine_routing')
      == {'service': 'default', 'version': 'test-version'})

resp = client.post('/_tasks/snapshot')
check('/_tasks/snapshot POST without queue header -> 403', resp.status_code == 403)

resp = client.post('/_tasks/snapshot', headers={'X-AppEngine-QueueName': 'default'})
check('/_tasks/snapshot POST with queue header -> 200', resp.status_code == 200)
with main.ndb_client.context():
  snapshots = models.CounterSnapshot.query().fetch()
  check('snapshot POST wrote a CounterSnapshot', len(snapshots) == 1
        and snapshots[0].count == 1)

resp = client.get('/_tasks/rainymood')
check('/_tasks/rainymood without cron header -> 403', resp.status_code == 403)

with mock.patch.object(main.requests, 'head') as mock_head:
  mock_head.return_value.status_code = 200
  resp = client.get('/_tasks/rainymood', headers={'X-Appengine-Cron': 'true'})
  check('/_tasks/rainymood healthy -> 200, primary url cached', resp.status_code == 200)
  cached = main._read_cache(main.RAINYMOOD_CACHE_KEY)
  check('rainymood cache set to primary url', cached['value'] == main.RAINYMOOD_URL)

with mock.patch.object(main.requests, 'head', side_effect=main.requests.RequestException('down')):
  resp = client.get('/_tasks/rainymood', headers={'X-Appengine-Cron': 'true'})
  check('/_tasks/rainymood when primary is down -> 200, falls back', resp.status_code == 200)
  cached = main._read_cache(main.RAINYMOOD_CACHE_KEY)
  check('rainymood cache switched to backup url', cached['value'] == main.BACKUP_RAINYMOOD_URL)

if failures:
  print('\nFAILURES: %r' % (failures,))
  sys.exit(1)
else:
  print('\nAll checks OK.')
