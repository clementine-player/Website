from google.appengine.api import memcache
from google.appengine.api import urlfetch

import requests
import webapp2

LAMBDA_URL=(
    'https://grzw1j1yvf.execute-api.us-east-1.amazonaws.com/prod/FetchBio')

MEMCACHE_KEY='bio/%s/%s'


class FetchBioPage(webapp2.RequestHandler):
  def get(self):
    self.response.headers['Content-Type'] = 'application/json'
    artist = self.request.get('artist')
    lang = self.request.get('lang')
    key = MEMCACHE_KEY % (artist, lang)
    data = memcache.get(key)
    if data is not None:
      self.response.out.write(data)
    else:
      response = requests.get(LAMBDA_URL, params={
          'artist': artist,
          'lang': lang,
      })
      memcache.add(key, response.text)
      self.response.out.write(response.text)


app = webapp2.WSGIApplication(
    [(r'/fetchbio', FetchBioPage)],
    debug=True)
