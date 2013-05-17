import jinja2
import json
import logging
import os
import urllib
import urllib2
import webapp2

from google.appengine.api import memcache
from google.appengine.api import taskqueue
from google.appengine.ext import db

jinja_environment = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)))

BUILDBOT_URL_TEMPLATE=('http://buildbot.clementine-player.org/json/' +
                       'builders/%s/builds/?')
SELECT_TEMPLATE='select=%s'

BUILDER='Mac Release'

BUILDERS=[
    ('Mac Release',          '/mac'),
    ('Deb Lucid 32-bit',     '/ubuntu-lucid'),
    ('Deb Lucid 64-bit',     '/ubuntu-lucid'),
    ('Deb Natty 32-bit',     '/ubuntu-natty'),
    ('Deb Natty 64-bit',     '/ubuntu-natty'),
    ('Deb Oneiric 32-bit',   '/ubuntu-oneiric'),
    ('Deb Oneiric 64-bit',   '/ubuntu-oneiric'),
    ('Deb Precise 32-bit',   '/ubuntu-precise'),
    ('Deb Precise 64-bit',   '/ubuntu-precise'),
    ('Deb Quantal 32-bit',   '/ubuntu-quantal'),
    ('Deb Quantal 64-bit',   '/ubuntu-quantal'),
    ('Deb Squeeze 32-bit',   '/debian-squeeze'),
    ('Deb Squeeze 64-bit',   '/debian-squeeze'),
    ('Deb Wheezy 32-bit',    '/debian-wheezy'),
    ('Deb Wheezy 64-bit',    '/debian-wheezy'),
    ('Rpm Fedora 16 32-bit', '/fedora-16'),
    ('Rpm Fedora 16 64-bit', '/fedora-16'),
    ('Rpm Fedora 17 32-bit', '/fedora-17'),
    ('Rpm Fedora 17 64-bit', '/fedora-17'),
    ('MinGW-w64 Release',    '/win32/release'),
]

BASE_BUILD_URL='http://builds.clementine-player.org'

LAST_BUILDS = ['-%d' % x for x in range(1, 6)]

class BuildResult(db.Model):
  builder = db.StringProperty()
  build_number = db.IntegerProperty()
  revision = db.StringProperty()
  filename = db.StringProperty()
  url = db.LinkProperty()

  def __str__(self):
    return '%s - %s - %s' % (self.build_number, self.revision, self.filename)

def GetLastSuccessfulBuild(builder, base_url):
  url = (BUILDBOT_URL_TEMPLATE % urllib.quote(builder)) + '&'.join([
      SELECT_TEMPLATE % x for x in LAST_BUILDS])

  request = urllib2.urlopen(url)
  data = json.load(request)

  last_successful_build = None
  for build in LAST_BUILDS:
    build = data[build]
    if build['currentStep']:
      continue
    if not build['text'][1] == 'successful':
      continue
    last_successful_build = build['number']
    properties = dict([(x[0], x[1]) for x in build['properties']])
    last_successful_build = BuildResult(
        key_name=builder,
        builder=builder,
        build_number=build['number'],
        revision=properties['got_revision'],
        filename=properties['output-filename'],
        url=(BASE_BUILD_URL + base_url + '/' +
                  properties['output-filename']))
    return last_successful_build


def RefreshLatestBuilds():
  for build in BUILDERS:
    taskqueue.add(
        url='/_tasks/refresh_build',
        params={
          'builder': build[0],
          'base_url': build[1],
        },
        queue_name='builds')


class RefreshBuildsPage(webapp2.RequestHandler):
  def get(self):
    RefreshLatestBuilds()


class RefreshBuildPage(webapp2.RequestHandler):
  def post(self):
    builder = self.request.get('builder')
    base_url = self.request.get('base_url')
    build = GetLastSuccessfulBuild(builder, base_url)
    if build is not None:
      build.put()
    else:
      logging.warning('No build for %s', builder)


class BuildsPage(webapp2.RequestHandler):
  def get(self):
    builds = memcache.get('builds')
    if builds is None:
      query = BuildResult.all()
      builds = query.fetch(30)
      if builds:
        memcache.set('builds', builds, time=300)

    self.RenderTemplate({'builds': builds})

  def RenderTemplate(self, params):
    template_path = os.path.join(os.path.dirname(__file__), 'builds.html')
    template = jinja_environment.get_template('builds.html')
    self.response.out.write(template.render(params))


app = webapp2.WSGIApplication(
    [
        ('/builds', BuildsPage),
        ('/_tasks/refresh_build', RefreshBuildPage),
        ('/_cron/refresh_builds', RefreshBuildsPage),
    ],
    debug=True)
