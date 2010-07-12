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
import tasks


class SparklePage(webapp.RequestHandler):
  TEMPLATE='sparkle.xml'
  def get(self):
    self.response.headers['Content-Type'] = 'text/xml'
    query = models.Version.all()
    path = os.path.join(os.path.dirname(__file__), self.TEMPLATE)
    self.response.out.write(template.render(path,
        { 'versions': query }))

    useragent = self.request.headers['User-Agent']
    if useragent:
      split = useragent.split(' ')
      if split:
        clementine = split[0]
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
        min_version=self.request.get('min_version'),
      )
    if new_version.put():
      self.response.out.write('OK')


class RainPage(webapp.RequestHandler):
  def get(self):
    self.redirect('http://s315939866.onlinehome.us/rainymood30a.mp3')
    taskqueue.add(url='/_tasks/counters', params={'key':'rain'})
    return


class HypnotoadPage(webapp.RequestHandler):
  def get(self):
    self.redirect('http://www.clementine-player.org/hypnotoad.mp3')
    taskqueue.add(url='/_tasks/counters', params={'key':'hypnotoad'})
    return


class CountersPage(webapp.RequestHandler):
  TEMPLATE='counters.html'
  def get(self):
    counters = tasks.Counter.all().fetch(10)
    data = [(x.key(), x.count) for x in counters]

    max_count = max([x.count for x in counters])
    chd = 't:%s' % ','.join([str(float(x.count) / max_count * 100) for x in counters])
    chxl = '0:|%s|' % '|'.join([x.key().name() for x in counters])

    url = ('http://chart.apis.google.com/chart?'
           'cht=bvg&chs=500x400&chd=%(chd)s&chxt=x,y'
           '&chxr=1,0,%(max)d,5&chbh=100,25,25'
           '&chxs=0,ff0000,12,0,lt|1,0000ff,10,1,lt&chxl=%(chxl)s')
    url = url % {'chd':chd, 'chxl':chxl, 'max':max_count}

    rows = [{'name':c.key().name(), 'count':c.count} for c in counters]

    path = os.path.join(os.path.dirname(__file__), self.TEMPLATE)
    self.response.out.write(template.render(path,
        { 'url': url,
          'counters': rows }))



application = webapp.WSGIApplication(
  [
    (r'/sparkle', SparklePage),
    (r'/versions', VersionsPage),
    (r'/rainymood', RainPage),
    (r'/hypnotoad', HypnotoadPage),
    (r'/counters', CountersPage),
  ],
  debug=True)

def main():
  run_wsgi_app(application)

if __name__ == '__main__':
  main()
