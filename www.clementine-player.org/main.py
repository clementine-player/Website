# -*- coding: utf-8 -*-

import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'settings'
from google.appengine.dist import use_library
use_library('django', '1.2')

# This has to be done before loading google.appengine.ext.webapp.template
import django.conf
django.conf.settings.configure(
  DEBUG=False,
  TEMPLATE_DEBUG=False,
  TEMPLATE_LOADERS=(
    'django.template.loaders.filesystem.load_template_source',
  ),
  LOCALE_PATHS=[os.path.join(os.path.dirname(__file__), "locale")],
)

from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app

from data import *
from django.template import RequestContext
from django.utils import translation
from django.utils.translation import ugettext as _

import copy
import datetime
import gettext
import logging
import re


class BasePage(webapp.RequestHandler):
  def MakePage(self, template_file, language, extra_params=None):
    root_page = "/"

    if language is None:
      # Guess the language
      self.request.COOKIES = {}
      self.request.META = os.environ

      language = translation.get_language_from_request(self.request)
      language.replace('-', '_')
      if not re.match(r'^[a-zA-Z]{2}(?:_[a-zA-Z]{2})?$', language):
        language = 'en'
    else:
      root_page = "/%s/" % language


    if extra_params is None:
      extra_params = {}

    # i18n
    translation.activate(language)
    self.request.LANGUAGE_CODE = translation.get_language()
    self.response.headers['Content-Language'] = translation.get_language()

    # Add extra display information to the list of downloads
    downloads = copy.deepcopy(DOWNLOADS)
    for d in downloads:
      display_os = DISPLAY_OS[d['os']]
      short_display_os = SHORT_DISPLAY_OS[d['os']]
      d['display_os'] = _(display_os)
      d['short_os'] = _(short_display_os)
      d['os_logo'] = OS_LOGOS[d['os']]

    # Add datetime objects to the list of news
    news = copy.deepcopy(NEWS)
    for n in news:
      title = n['title']
      content = n['content']
      n['datetime'] = datetime.datetime.fromtimestamp(n['timestamp'])
      n['title'] = _(title)
      n['content'] = _(content)

    screenshots = copy.deepcopy(SCREENSHOTS)
    for s in screenshots:
      for e in s['entries']:
        title = e['title']
        e['title'] = _(title)

    # Try to detect the user's OS and architecture
    ua = self.request.headers['User-Agent'].lower()
    if 'win' in ua:
      best_download = self.FindDownload('windows')
    elif 'mac' in ua:
      best_download = self.FindDownload('snowleopard')
    elif 'fedora' in ua:
      if '64' in ua:
        best_download = self.FindDownload('fedora16', 64)
      else:
        best_download = self.FindDownload('fedora16', 32)
    elif 'maverick' in ua:
      if '64' in ua:
        best_download = self.FindDownload('umaverick', 64)
      else:
        best_download = self.FindDownload('umaverick', 32)
    elif 'lucid' in ua:
      if '64' in ua:
        best_download = self.FindDownload('ubuntu', 64)
      else:
        best_download = self.FindDownload('ubuntu', 32)
    else:
      best_download = None

    # Translate the best download strings
    if best_download is not None:
      display_os = DISPLAY_OS[best_download['os']]
      short_display_os = SHORT_DISPLAY_OS[best_download['os']]
      best_download['display_os'] = _(display_os)
      best_download['short_os'] = _(short_display_os)
      best_download['os_logo'] = OS_LOGOS[best_download['os']]

    languages = [{'code': x, 'name': LANGUAGE_NAMES[x], 'current': x == language} for x in LANGUAGES]

    params = {
      'best_download':      best_download,
      'download_base_url':  DOWNLOAD_BASE_URL,
      'downloads':          downloads,
      'latest_downloads':   [x for x in downloads if x['ver'] == LATEST_VERSION],
      'latest_screenshots': screenshots[0]['entries'],
      'latest_version':     LATEST_VERSION,
      'news':               news,
      'language':           language,
      'languages':          languages,
      'old_downloads':      [x for x in downloads if x['ver'] != LATEST_VERSION],
      'root_page':          root_page,
      'screenshots':        screenshots,
    }
    params.update(extra_params)

    path = os.path.join(os.path.dirname(__file__), template_file)

    t = template.load(path)
    self.response.out.write(t.render(RequestContext(self.request, params)))

  def FindDownload(self, os, arch=0):
    return copy.deepcopy([x for x in DOWNLOADS if x['os'] == os
                                              and x['arch'] == arch
                                              and x['ver'] == LATEST_VERSION][0])


class MainPage(BasePage):
  def get(self, language):
    self.MakePage('main.html', language)

class ScreenshotsPage(BasePage):
  def get(self, language):
    self.MakePage('screenshots.html', language)

class DownloadsPage(BasePage):
  def get(self, language):
    self.MakePage('downloads.html', language)

class ParticipatePage(BasePage):
  def get(self, language):
    self.MakePage('participate.html', language)

class WiimotePage(webapp.RequestHandler):
  def get(self):
    self.redirect('http://code.google.com/p/clementine-player/wiki/WiiRemotes')


LANG_RE = r'/(?:([a-zA-Z]{2}(?:_[a-zA-Z]{2})?)/?)?'
application = webapp.WSGIApplication(
  [
    (LANG_RE + '',            MainPage),
    (LANG_RE + 'about',       MainPage),
    (LANG_RE + 'screenshots', ScreenshotsPage),
    (LANG_RE + 'downloads',   DownloadsPage),
    (LANG_RE + 'participate', ParticipatePage),
    (r'/wiimote',             WiimotePage),
  ],
  debug=True)

def main():
  run_wsgi_app(application)

if __name__ == '__main__':
  main()
