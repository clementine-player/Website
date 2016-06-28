from google.appengine.api import memcache
from google.appengine.api import urlfetch

import webapp2

LAMBDA_URL=(
    'https://grzw1j1yvf.execute-api.us-east-1.amazonaws.com/prod/FetchBio'
    '?artist=%s&lang=%s')

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
      url = LAMBDA_URL % (artist, lang)
      response = urlfetch.fetch(url)
      memcache.add(key, response.content)
      self.response.out.write(response.content)


app = webapp2.WSGIApplication(
    [(r'/fetchbio', FetchBioPage)],
    debug=True)
