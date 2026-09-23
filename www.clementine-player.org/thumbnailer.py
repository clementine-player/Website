# -*- coding: utf-8 -*-

import io
import logging

import requests
from flask import Blueprint, Response, request
from google.cloud import datastore
from PIL import Image

WIDTH = 440

thumbnailer = Blueprint('thumbnailer', __name__)

_datastore_client = None


def _get_datastore_client():
  global _datastore_client
  if _datastore_client is None:
    _datastore_client = datastore.Client()
  return _datastore_client


@thumbnailer.route('/thumbnails/<path:filename>')
def thumbnail(filename):
  client = _get_datastore_client()
  key = client.key('Thumbnail', filename)
  entity = client.get(key)

  if entity is None:
    url = '%s://%s/screenshots/%s' % (request.scheme, request.host, filename)
    logging.info(url)
    result = requests.get(url)
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
