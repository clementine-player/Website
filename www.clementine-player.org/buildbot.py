import json
import os
import urllib
import urllib2

from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app

BUILDBOT_URL_TEMPLATE=('http://buildbot.clementine-player.org/json/' +
                       'builders/%s/builds/?')
SELECT_TEMPLATE='select=%s'

BUILDER='Mac Release'

BUILDERS=[
    'Mac Release',
    'Deb Lucid 32-bit',
    'Deb Lucid 64-bit',
    'Deb Natty 32-bit',
    'Deb Natty 64-bit',
    'Deb Oneiric 32-bit',
    'Deb Oneiric 64-bit',
    'Deb Precise 32-bit',
    'Deb Precise 64-bit',
    'Deb Quantal 32-bit',
    'Deb Quantal 64-bit',
    'MinGW-w64 Release',
]

LAST_BUILDS = ['-%d' % x for x in range(1, 6)]

class BuildResult(object):
  def __init__(self, builder, build_number, revision, filename):
    self.builder = builder
    self.build_number = build_number
    self.revision = revision
    self.filename = filename

  def __str__(self):
    return '%s - %s - %s' % (self.build_number, self.revision, self.filename)

def GetLastSuccessfulBuild(builder):
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
        builder,
        build['number'],
        properties['got_revision'],
        properties['output-filename'])
    return last_successful_build


class BuildsPage(webapp.RequestHandler):
  def get(self):
    builds = [GetLastSuccessfulBuild(x) for x in BUILDERS]
    self.RenderTemplate({'builds': builds})

  def RenderTemplate(self, params):
    template_path = os.path.join(os.path.dirname(__file__), 'builds.html')
    self.response.out.write(template.render(template_path, params))


application = webapp.WSGIApplication(
    [
        ('/builds', BuildsPage),
    ],
    debug=True)


def main():
  run_wsgi_app(application)

if __name__ == '__main__':
  main()
