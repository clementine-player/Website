import os

from google.appengine.api import memcache
from google.appengine.api import urlfetch
from google.appengine.api import users
from google.appengine.api import xmpp
from google.appengine.api.labs import taskqueue
from google.appengine.ext import db
from google.appengine.ext.webapp import template

import colorsys
import hmac
import json
import logging
import webapp2

import pygooglechart
from pygooglechart import StackedVerticalBarChart
from pygooglechart import SimpleLineChart

import models
import tasks

RAINYMOOD_URL = 'http://173.193.205.68/audio/RainyMood.mp3'
BACKUP_RAINYMOOD_URL = 'http://images.clementine-player.org/RainyMood.mp3'
ICECAST_URL   = 'http://dir.xiph.org/yp.xml'

RAINYMOOD_MEMCACHE_KEY = 'rainymood'

SPARKLE_MEMCACHE_KEY = 'sparkle-%s'

class SparklePageBase(webapp2.RequestHandler):
  def FetchVersions(self, platform):
    cached_versions = memcache.get(SPARKLE_MEMCACHE_KEY % platform)
    if cached_versions is None:
      query = models.Version.all()
      query.filter('platform =', platform)
      versions = query.fetch(20)
      memcache.set(SPARKLE_MEMCACHE_KEY % platform, versions)
      return versions
    else:
      return cached_versions


  def WriteResponse(self, template_name, platform):
    versions = self.FetchVersions(platform)

    self.response.headers['Content-Type'] = 'text/xml'
    path = os.path.join(os.path.dirname(__file__), template_name)
    self.response.out.write(template.render(path,
        { 'versions': versions }))

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


class VersionsPage(webapp2.RequestHandler):
  TEMPLATE='versions.html'
  def get(self):
    versions_mac = models.Version.all()
    versions_mac.filter('platform =', 'mac')

    versions_win = models.Version.all()
    versions_win.filter('platform =', 'windows')

    path = os.path.join(os.path.dirname(__file__), self.TEMPLATE)
    self.response.out.write(template.render(path, {
        'versions_mac': versions_mac,
        'versions_win': versions_win,
    }))

  def post(self):
    new_version = models.Version(
        platform       = self.request.get('platform'),
        revision       = self.request.get('revision'),
        version        = self.request.get('version'),
        signature      = self.request.get('signature'),
        download_link  = self.request.get('download_link'),
        changelog_link = self.request.get('changelog_link'),
        bundle_size    = int(self.request.get('bundle_size', 0)),
        min_version    = self.request.get('min_version'),
    )

    if new_version.put():
      self.redirect("/versions")


class RainPage(webapp2.RequestHandler):
  def get(self):
    url = memcache.get(RAINYMOOD_MEMCACHE_KEY)
    if url is None:
      # Default to serving from rainymood.com
      url = RAINYMOOD_URL
      memcache.set(RAINYMOOD_MEMCACHE_KEY, url)
    self.redirect(url)
    try:
      taskqueue.add(url='/_tasks/counters', params={'key':'rain'})
    except taskqueue.Error, e:
      logging.warning('Failed to add task: %s', e)
    return


class IcecastPage(webapp2.RequestHandler):
  def get(self):
    self.redirect(ICECAST_URL)
    try:
      taskqueue.add(url='/_tasks/counters', params={'key':'icecast-directory'})
    except taskqueue.Error, e:
      logging.warning('Failed to add task: %s', e)
    return


class CountersPage(webapp2.RequestHandler):
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


class GeolocatePage(webapp2.RequestHandler):
  def get(self):
    if ('X-Appengine-City' in self.request.headers and
        'X-Appengine-Citylatlong' in self.request.headers and
        'X-Appengine-Country' in self.request.headers):
      data = {
        'city': self.request.headers['X-Appengine-City'],
        'latlng': self.request.headers['X-Appengine-Citylatlong'],
        'country': self.request.headers['X-Appengine-Country']
      }
      json.dump(data, self.response.out)
    else:
      self.error(404)


app = webapp2.WSGIApplication(
  [
    (r'/sparkle', MacSparklePage),
    (r'/sparkle-windows', WinSparklePage),
    (r'/versions', VersionsPage),
    (r'/rainymood', RainPage),
    (r'/counters', CountersPage),
    (r'/icecast-directory', IcecastPage),
    (r'/geolocate', GeolocatePage),
  ],
  debug=True)
