# -*- coding: utf-8 -*-

import io
import logging
import re

import requests
from flask import Blueprint, Response, abort, request
from google.cloud import datastore
from PIL import Image

import android

WIDTH = 440
# Content-addressed, so they never change.
FOREVER = 'public, max-age=31536000, immutable'
# Clementine release screenshots are kept by their SHA-256, or their asset's id.
RELEASE_KEY = re.compile(r'([0-9a-f]{64}|id[0-9]+)$')
# Its full size is kept too, for a Datastore entity: under its 1 MiB.
MAX_KEPT_BYTES = 1000000

# Set by main: the download URL of the newest Clementine release's screenshot
# with a key, or None.
release_screenshot_url = None

thumbnailer = Blueprint('thumbnailer', __name__)

_datastore_client = None


def _get_datastore_client():
  global _datastore_client
  if _datastore_client is None:
    _datastore_client = datastore.Client()
  return _datastore_client


@thumbnailer.route('/thumbnails/android/<tag>/<int:number>.png')
def android_thumbnail(tag, number):
  # Only Clementine Remote's own store screenshots, at a release's tag.
  if not android.TAG.match(tag) or not 1 <= number <= android.MAX_SCREENSHOTS:
    abort(404)
  return _thumbnail('android/%s/%d.png' % (tag, number),
                    android.screenshot_url(tag, number))


@thumbnailer.route('/thumbnails/release/<key>.png')
def release_thumbnail(key):
  if not RELEASE_KEY.match(key):
    abort(404)
  return _thumbnail('release/' + key, lambda: release_screenshot_url(key),
                    cache_control=FOREVER)


@thumbnailer.route('/release-screenshots/<key>.png')
def release_screenshot(key):
  # The full size, from the site rather than GitHub, which serves release
  # files as downloads rather than images.
  if not RELEASE_KEY.match(key):
    abort(404)
  client = _get_datastore_client()
  entity_key = client.key('ReleaseScreenshot', key)
  entity = client.get(entity_key)
  if entity is not None:
    data = entity['data']
  else:
    data = _download(release_screenshot_url(key))
    if len(data) < MAX_KEPT_BYTES:
      entity = datastore.Entity(entity_key, exclude_from_indexes=('data',))
      entity.update({'data': data})
      client.put(entity)
  response = Response(data, mimetype='image/png')
  response.headers['Cache-Control'] = FOREVER
  return response


@thumbnailer.route('/thumbnails/<path:filename>')
def thumbnail(filename):
  return _thumbnail(filename, '%s://%s/screenshots/%s' % (request.scheme, request.host, filename))


def _download(url):
  if url is None:
    abort(404)
  logging.info(url)
  result = requests.get(url, timeout=20)
  if result.status_code == 404:
    abort(404)
  result.raise_for_status()
  return result.content


def _thumbnail(name, url, cache_control='public, max-age=86400'):
  # |url| can be a function, so it's only worked out when it's needed.
  client = _get_datastore_client()
  key = client.key('Thumbnail', name)
  entity = client.get(key)

  if entity is None:
    image = Image.open(io.BytesIO(_download(url() if callable(url) else url)))
    height = int(image.height * (WIDTH / float(image.width)))
    image = image.resize((WIDTH, height), Image.LANCZOS)

    buf = io.BytesIO()
    image.save(buf, format='PNG')
    data = buf.getvalue()

    entity = datastore.Entity(key, exclude_from_indexes=('data',))
    entity.update({'data': data})
    client.put(entity)
  else:
    data = entity['data']

  response = Response(data, mimetype='image/png')
  response.headers['Cache-Control'] = cache_control
  return response
