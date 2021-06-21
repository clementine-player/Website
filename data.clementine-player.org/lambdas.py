from google.appengine.api import memcache
from google.appengine.api import urlfetch

import requests
import webapp2

BIO_URL = 'https://bio-5ctfinxp4a-lz.a.run.app/'
IMAGES_URL = 'https://images-5ctfinxp4a-lz.a.run.app/'

BIO_KEY = 'bio/%s/%s'
IMAGES_KEY = 'images/%s'


class FetchBioPage(webapp2.RequestHandler):

  def get(self):
    self.response.headers['Content-Type'] = 'application/json; charset=utf-8'
    artist = self.request.get('artist')
    lang = self.request.get('lang')
    key = BIO_KEY % (artist, lang)
    data = memcache.get(key)
    if data is not None:
      self.response.out.write(data)
    else:
      response = requests.get(
          BIO_URL, params={
              'artist': artist,
              'lang': lang,
          })
      memcache.add(key, response.text)
      self.response.out.write(response.text)


class FetchImagesPage(webapp2.RequestHandler):

  def get(self):
    self.response.headers['Content-Type'] = 'application/json; charset=utf-8'
    artist = self.request.get('artist')
    key = IMAGES_KEY % artist
    data = memcache.get(key)
    if data is not None:
      self.response.out.write(data)
    else:
      response = requests.get(
          IMAGES_URL, params={
              'artist': artist,
          })
      memcache.add(key, response.text)
      self.response.out.write(response.text)


app = webapp2.WSGIApplication(
    [(r'/fetchbio', FetchBioPage), (r'/fetchimages', FetchImagesPage)],
    debug=True)
