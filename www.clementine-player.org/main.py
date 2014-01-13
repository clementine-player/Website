# -*- coding: utf-8 -*-

import babel
import jinja2
import os
import webapp2

from webapp2_extras import i18n

from data import DISPLAY_OS
from data import DOWNLOAD_BASE_URL
from data import DOWNLOADS
from data import LANGUAGE_NAMES
from data import LANGUAGES
from data import LATEST_VERSION
from data import NEWS
from data import OS_LOGOS
from data import SCREENSHOTS
from data import SHORT_DISPLAY_OS

jinja_environment = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions=['jinja2.ext.i18n', 'jinja2.ext.with_'])
jinja_environment.install_gettext_translations(i18n)

def format_datetime(value, language='en'):
  # Babel supports fewer locales than we do so change to English for 
  # unsupported locales.
  if not babel.localedata.exists(language):
    language = 'en'
  return babel.dates.format_date(value, format='full', locale=language)
jinja_environment.filters['datetime'] = format_datetime

import copy
import datetime
import gettext
import logging
import re


class BasePage(webapp2.RequestHandler):
  def MakePage(self, template_file, language, extra_params=None):
    root_page = "/"

    if language is None:
      language = self.GetLanguageFromRequest()
    else:
      root_page = "/%s/" % language

    if language is None:
      language = 'en'

    i18n.get_i18n().set_locale(language)

    if extra_params is None:
      extra_params = {}

    # i18n
    self.response.headers['Content-Language'] = i18n.get_i18n().locale

    # Add extra display information to the list of downloads
    downloads = copy.deepcopy(DOWNLOADS)
    for d in downloads:
      display_os = DISPLAY_OS[d['os']]
      short_display_os = SHORT_DISPLAY_OS[d['os']]
      d['display_os'] = i18n.gettext(display_os)
      d['short_os'] = i18n.gettext(short_display_os)
      d['os_logo'] = OS_LOGOS[d['os']]

    # Add datetime objects to the list of news
    news = copy.deepcopy(NEWS)
    for n in news:
      title = n['title']
      content = n['content']
      n['datetime'] = datetime.datetime.fromtimestamp(n['timestamp'])
      n['title'] = i18n.gettext(title)
      n['content'] = i18n.gettext(content)

    screenshots = copy.deepcopy(SCREENSHOTS)
    for s in screenshots:
      for e in s['entries']:
        title = e['title']
        e['title'] = i18n.gettext(title)

    # Try to detect the user's OS and architecture
    ua = self.request.headers['User-Agent'].lower()
    if 'win' in ua:
      best_download = self.FindDownload('windows')
    elif 'mac' in ua:
      best_download = self.FindDownload('lion')
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
      best_download['display_os'] = i18n.gettext(display_os)
      best_download['short_os'] = i18n.gettext(short_display_os)
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
      'is_rtl':             language == 'ar' or language == 'fa',
    }
    params.update(extra_params)

    template = jinja_environment.get_template(template_file)
    self.response.out.write(template.render(params))

  def FindDownload(self, os, arch=0):
    return copy.deepcopy([x for x in DOWNLOADS if x['os'] == os
                                              and x['arch'] == arch
                                              and x['ver'] == LATEST_VERSION][0])

  # Similar to django.utils.translation.get_language_from_request which has no equivalent in jinja2
  def GetLanguageFromRequest(self):
    if not 'Accept-Language' in self.request.headers:
      return None

    accepted_languages_header = self.request.headers['Accept-Language']
    accepted_languages = [language.split(';')[0].replace('-', '_').lower() for language in accepted_languages_header.split(',')]
    for accepted_language in accepted_languages:
      if accepted_language in [language.lower() for language in LANGUAGES]:
        return accepted_language
    return None


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

class WiimotePage(webapp2.RequestHandler):
  def get(self):
    self.redirect('https://github.com/clementine-player/Clementine/wiki/Wii-Remotes')


config = {}
config['webapp2_extras.i18n'] = {
    'domains': ['django'],
    'translations_path': os.path.join(os.path.dirname(__file__), 'locale'),
}

LANG_RE = r'/(?:([a-zA-Z]{2}(?:_[a-zA-Z]{2})?)/?)?'
app = webapp2.WSGIApplication(
  [
    (LANG_RE + '',            MainPage),
    (LANG_RE + 'about',       MainPage),
    (LANG_RE + 'screenshots', ScreenshotsPage),
    (LANG_RE + 'downloads',   DownloadsPage),
    (LANG_RE + 'participate', ParticipatePage),
    (r'/wiimote',             WiimotePage),
  ],
  config=config,
  debug=True)
