# -*- coding: utf-8 -*-

import io
import logging

import requests
from flask import Blueprint, Response, abort, request
from google.cloud import datastore
from PIL import Image

import android

WIDTH = 440

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


@thumbnailer.route('/thumbnails/<path:filename>')
def thumbnail(filename):
  return _thumbnail(filename, '%s://%s/screenshots/%s' % (request.scheme, request.host, filename))


def _thumbnail(name, url):
  client = _get_datastore_client()
  key = client.key('Thumbnail', name)
  entity = client.get(key)

  if entity is None:
    logging.info(url)
    result = requests.get(url, timeout=20)
    if result.status_code == 404:
      abort(404)
    result.raise_for_status()

    image = Image.open(io.BytesIO(result.content))
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
  response.headers['Cache-Control'] = 'public, max-age=86400'
  return response
