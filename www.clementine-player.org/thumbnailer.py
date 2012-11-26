# -*- coding: utf-8 -*-

import os
import webapp2

from google.appengine.api import images
from google.appengine.api import memcache
from google.appengine.api import urlfetch

import logging
import urlparse

MEMCACHE_NAMESPACE = 'thumbnailer'
WIDTH = 440

class Thumbnailer(webapp2.RequestHandler):
  def get(self, filename):
    # Check memcache first
    data = memcache.get(filename, MEMCACHE_NAMESPACE)

    if data is None:
      # Construct the full URL to the original image
      request_url = urlparse.urlparse(self.request.url)

      url = "%s://%s/screenshots/%s" % (
        request_url.scheme,
        request_url.netloc,
        filename)
      url = url.replace('8080', '8081') # Because the dev server is single threaded
      logging.info(url)

      # Fetch the original image
      result = urlfetch.fetch(url)

      # Load it and resize it
      image = images.Image(image_data=result.content)
      image.resize(width=WIDTH)
      data = image.execute_transforms(output_encoding=images.PNG)

      # Put it in memcache
      memcache.set(filename, data, namespace=MEMCACHE_NAMESPACE)

    self.response.headers['Content-Type'] = 'image/png'
    self.response.headers['Cache-Control'] = 'public, max-age=86400'
    self.response.out.write(data)


app = webapp2.WSGIApplication(
  [
    (r'/thumbnails/([a-zA-Z0-9\.-]*)', Thumbnailer),
  ],
  debug=True)
