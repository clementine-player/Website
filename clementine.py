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

import colorsys
import hmac
import logging

import pygooglechart
from pygooglechart import StackedVerticalBarChart
from pygooglechart import SimpleLineChart

import models
import tasks

RAINYMOOD_URL = 'http://www.rainymood.com/audio/RainyMood.mp3'
ICECAST_URL   = 'http://dir.xiph.org/yp.xml'

class SparklePageBase(webapp.RequestHandler):
  def WriteResponse(self, template_name, platform):
    self.response.headers['Content-Type'] = 'text/xml'
    query = models.Version.all()
    query.filter('platform =', platform)
    path = os.path.join(os.path.dirname(__file__), template_name)
    self.response.out.write(template.render(path,
        { 'versions': query }))

    useragent = self.request.headers['User-Agent']
    if useragent:
      split = useragent.split(' ')
      if split:
        clementine = split[0]
        try:
          taskqueue.add(url='/_tasks/counters', params={'key':clementine})
        except taskqueue.Error, e:
          logging.warning('Failed to add task: %s', e)


class MacSparklePage(SparklePageBase):
  def get(self):
    self.WriteResponse('sparkle.xml', 'mac')


class WinSparklePage(SparklePageBase):
  def get(self):
    self.WriteResponse('winsparkle.xml', 'windows')


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
    self.redirect(RAINYMOOD_URL)
    try:
      taskqueue.add(url='/_tasks/counters', params={'key':'rain'})
    except taskqueue.Error, e:
      logging.warning('Failed to add task: %s', e)
    return


class IcecastPage(webapp.RequestHandler):
  def get(self):
    self.redirect(ICECAST_URL)
    try:
      taskqueue.add(url='/_tasks/counters', params={'key':'icecast-directory'})
    except taskqueue.Error, e:
      logging.warning('Failed to add task: %s', e)
    return


class CountersPage(webapp.RequestHandler):
  TEMPLATE='counters.html'
  def get(self):
    counters = tasks.Counter.all().fetch(10)

    rows = [{'name':c.key().name(), 'count':c.count} for c in counters]

    chart = SimpleLineChart(1000, 300)
    for counter in counters:
      query = counter.snapshots
      query.order('-date')
      snapshots = query.fetch(30)
      counts = [s.count for s in snapshots]
      dates = [s.date.strftime("%d/%m") for s in snapshots]
      for i in xrange(len(counts) - 1):
        counts[i] -= counts[i+1]
      counts.reverse()
      dates.reverse()
      chart.add_data(counts[1:])

    chart.set_axis_labels(pygooglechart.Axis.BOTTOM, dates[1:])
    chart.set_axis_labels(pygooglechart.Axis.LEFT, range(0, chart.data_y_range()[1], 5))

    hsv_colours = [(float(x) / 255, 1, 1) for x in range(0, 255, 255 / len(counters))]
    rgb_colours = [colorsys.hsv_to_rgb(*x) for x in hsv_colours]
    hex_colours = ['%02x%02x%02x' % (int(x[0] * 255), int(x[1] * 255), int(x[2] * 255)) for x in rgb_colours]

    chart.set_colours(hex_colours)
    chart.set_legend([c.key().name() for c in counters])

    path = os.path.join(os.path.dirname(__file__), self.TEMPLATE)
    self.response.out.write(template.render(path,
        { 'url': chart.get_url(),
          'counters': rows }))


application = webapp.WSGIApplication(
  [
    (r'/sparkle', MacSparklePage),
    (r'/sparkle-windows', WinSparklePage),
    (r'/versions', VersionsPage),
    (r'/rainymood', RainPage),
    (r'/counters', CountersPage),
    (r'/icecast-directory', IcecastPage),
  ],
  debug=True)

def main():
  run_wsgi_app(application)

if __name__ == '__main__':
  main()
