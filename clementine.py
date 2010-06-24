import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'settings'
from google.appengine.dist import use_library
use_library('django', '1.1')

from google.appengine.api import urlfetch
from google.appengine.api import users
from google.appengine.api import xmpp
from google.appengine.api.labs import taskqueue
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app

from django.utils import simplejson

import hmac
import logging

import models


class SparklePage(webapp.RequestHandler):
  TEMPLATE='sparkle.xml'
  def get(self):
    self.response.headers['Content-Type'] = 'text/xml'
    query = models.Version.all()
    path = os.path.join(os.path.dirname(__file__), self.TEMPLATE)
    self.response.out.write(template.render(path,
        { 'versions': query }))

    useragent = self.request.headers['User-Agent']
    clementine = useragent.split(' ')[0]
    taskqueue.add(url='/_tasks/counters', params={'key':clementine})


class VersionsPage(webapp.RequestHandler):
  TEMPLATE='versions.html'
  def get(self):
    query = models.Version.all()
    path = os.path.join(os.path.dirname(__file__), self.TEMPLATE)
    self.response.out.write(template.render(path,
        { 'versions': query }))

  def post(self):
    self.response.out.write(self.request.body)

    new_version = models.Version(
        revision=int(self.request.get('revision')),
        version=self.request.get('version'),
        signature=self.request.get('signature'),
        download_link=self.request.get('download_link'),
        changelog_link=self.request.get('changelog_link'),
        changelog=self.request.get('changelog'),
        bundle_size=int(self.request.get('bundle_size')),
      )
    if new_version.put():
      self.response.out.write('OK')


class RainPage(webapp.RequestHandler):
  def get(self):
    self.redirect('http://s315939866.onlinehome.us/rainymood30a.mp3')
    taskqueue.add(url='/_tasks/counters', params={'key':'rain'})
    return


application = webapp.WSGIApplication(
  [
    (r'/sparkle', SparklePage),
    (r'/versions', VersionsPage),
    (r'/rainymood', RainPage),
  ],
  debug=True)

def main():
  run_wsgi_app(application)

if __name__ == '__main__':
  main()
