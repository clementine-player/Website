# -*- coding: utf-8 -*-

import babel
import jinja2
import os
import re
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

from data import DEBIAN_NAMES
from data import UBUNTU_NAMES

def _(x): return x

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
import json
import logging
import re

from google.appengine.api import app_identity
from google.appengine.api import urlfetch


class Error(Exception):
  pass


class GithubFetchError(Error):
  pass


class BasePage(webapp2.RequestHandler):
  def _FetchRelease(self):
    r = urlfetch.fetch('https://api.github.com/repos/clementine-player/Clementine/releases/latest')
    if r.status_code != 200:
      raise GithubFetchError('Error fetching releases: %d %s' % (r.status_code, r.content))
    result = json.loads(r.content)
    downloads = []
    for asset in result['assets']:
      info = {
        'os': 'Unknown',
        'ver': result['tag_name'],
        'arch': 0,
        'url': asset['browser_download_url'],
      }
      if asset['content_type'] == 'application/x-rpm':
        info['os'] = 'fedora'
        info['short_os'] = 'Fedora'
        info['os_logo'] = 'fedora-logo.png'
        if 'x86_64' in asset['name']:
          info['arch'] = 64
        elif 'i686' in asset['name']:
          info['arch'] = 32
        m = re.search(r'\.fc(\d+)\.', asset['name'])
        if m:
          v = m.group(1)
          info['display_os'] = 'Fedora %s' % v
        else:
          info['display_os'] = 'Fedora'
      elif asset['content_type'] == 'application/x-apple-diskimage':
        info['os'] = 'mac'
        info['display_os'] = 'Mac'
        info['short_os'] = 'Mac'
        info['os_logo'] = 'leopard-logo.png'
        info['arch'] = 64
      elif asset['content_type'] == 'application/x-xz':
        info['os'] = 'source'
        info['display_os'] = _('Source Code')
        info['short_os'] = _('Source')
        info['os_logo'] = 'source-logo.png'
      elif asset['content_type'] == 'application/x-ms-dos-executable':
        info['os'] = 'windows'
        info['display_os'] = 'Windows'
        info['short_os'] = 'Windows'
        info['os_logo'] = 'windows-logo.png'
        info['arch'] = 32
      elif asset['content_type'] == 'application/x-deb' or asset['content_type'] == 'application/vnd.debian.binary-package':
        for n in DEBIAN_NAMES:
          if n in asset['name']:
            info['os'] = 'debian'
            info['display_os'] = 'Debian %s' % n.capitalize()
            info['short_os'] = n.capitalize()
            info['os_logo'] = 'squeeze-logo.png'

        for n in UBUNTU_NAMES:
          if n in asset['name']:
            info['os'] = 'ubuntu'
            info['display_os'] = 'Ubuntu %s' % n.capitalize()
            info['short_os'] = n.capitalize()
            info['os_logo'] = 'ubuntu-logo.png'

        if 'i386' in asset['name']:
          info['arch'] = 32
        elif 'amd64' in asset['name']:
          info['arch'] = 64
        elif 'armhf' in asset['name']:
          info['arch'] = 32
          info['display_os'] = 'Raspberry Pi'
          info['short_os'] = 'RPI'
          info['os_logo'] = 'raspberry-pi-logo.png'
        
      downloads.append(info)
    return downloads


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

    downloads = self._FetchRelease()

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
      best_download = self.FindDownload(downloads, 'windows', 32)
    elif 'mac' in ua:
      best_download = self.FindDownload(downloads, 'mac', 64)
    elif 'fedora' in ua:
      if '64' in ua:
        best_download = self.FindDownload(downloads, 'fedora', 64)
      else:
        best_download = self.FindDownload(downloads, 'fedora', 32)
    else:
      best_download = None

    languages = [{'code': x, 'name': LANGUAGE_NAMES[x], 'current': x == language} for x in LANGUAGES]

    params = {
      'best_download':      best_download,
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
      'is_rtl':             language == 'ar' or language == 'fa' or language == 'he',
    }
    params.update(extra_params)

    template = jinja_environment.get_template(template_file)
    self.response.out.write(template.render(params))

  def FindDownload(self, downloads, os, arch=0):
    downloads = [x for x in downloads if x['os'] == os
                                      and x['arch'] == arch
                                      and x['ver'][:3] == LATEST_VERSION[:3]]
    if downloads:
      return copy.deepcopy(downloads[0])
    else:
      return None

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

class PrivacyPage(BasePage):
  def get(self, language):
    self.MakePage('privacy.html', language)

class AcmeChallengePage(webapp2.RequestHandler):
  def get(self):
    self.redirect(
        'https://builds.clementine-player.org' + self.request.path)

  def post(self):
    self.redirect(
        'https://builds.clementine-player.org' + self.request.path)

class TransifexPullPage(webapp2.RequestHandler):
  def get(self):
    token, _ = app_identity.get_access_token('https://www.googleapis.com/auth/cloud-platform')
    response = urlfetch.fetch(
        'https://cloudbuild.googleapis.com/v1/projects/clementine-web/triggers/e19d2c38-5478-4282-a475-ee54d6d5363a:run',
        method=urlfetch.POST,
        payload=json.dumps({
            'projectId': 'clementine-web',
            'repoName': 'github-clementine-player-website',
            'branchName': 'master',
        }),
        headers={
          'Authorization': 'Bearer {}'.format(token),
          'Content-Type': 'application/json',
        })
    if response.status_code != 200:
      raise Exception('Triggering build failed: {}'.format(response.content))
    result = json.loads(response.content)
    self.response.headers['Content-Type'] = 'application/json'
    self.response.write(json.dumps(result, indent=2))

config = {}
config['webapp2_extras.i18n'] = {
    'domains': ['django'],
    'translations_path': os.path.join(os.path.dirname(__file__), 'locale'),
}

LANG_RE = r'/(?:([a-zA-Z]{2}(?:_[a-zA-Z]{2})?(?:@latin)?)/?)?'
app = webapp2.WSGIApplication(
  [
    (LANG_RE + '',            MainPage),
    (LANG_RE + 'about',       MainPage),
    (LANG_RE + 'screenshots', ScreenshotsPage),
    (LANG_RE + 'downloads',   DownloadsPage),
    (LANG_RE + 'participate', ParticipatePage),
    (LANG_RE + 'privacy',     PrivacyPage),
    (r'/wiimote',             WiimotePage),
    (r'/.well-known/acme-challenge/.*', AcmeChallengePage),
    (r'/scheduled/trigger-transifex-pull', TransifexPullPage),
  ],
  config=config,
  debug=True)
