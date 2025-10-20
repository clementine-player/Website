# -*- coding: utf-8 -*-

import babel
from flask import Flask, render_template, request, g, redirect, send_file, jsonify
from flask_babel import Babel, gettext
from PIL import Image
import io
import google.auth

import data
import copy
import datetime
import json
import re
import os
import requests
from cachelib import SimpleCache

app = Flask(__name__)
babel_ext = Babel(app)
cache = SimpleCache()

GITHUB_TOKEN=os.environ.get('GITHUB_TOKEN')
RELEASES_KEY='github_releases'

@app.before_request
def before_request():
    path_parts = request.path.split('/')
    if len(path_parts) > 1 and path_parts[1] in data.LANGUAGES:
        g.language = path_parts[1]
    else:
        g.language = request.accept_languages.best_match(data.LANGUAGES)
    if g.language is None:
        g.language = 'en'
    g.locale = g.language


@babel_ext.locale_selector
def get_locale():
    return g.get('locale', 'en')

def format_datetime(value, language='en'):
    if not babel.localedata.exists(language):
        language = 'en'
    return babel.dates.format_date(value, format='full', locale=language)

app.jinja_env.filters['datetime'] = format_datetime

def _fetch_release():
    content = cache.get(RELEASES_KEY)
    if content is None:
      if not GITHUB_TOKEN:
          return []
      auth_header = 'token %s' % GITHUB_TOKEN
      r = requests.get('https://api.github.com/repos/clementine-player/Clementine/releases/latest', headers={
        'Authorization': auth_header,
      })
      if r.status_code != 200:
        raise Exception('Error fetching releases: %d %s' % (r.status_code, r.text))
      cache.set(RELEASES_KEY, r.text, timeout=60*60)
      content = r.text

    result = json.loads(content)
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
        info['display_os'] = gettext('Source Code')
        info['short_os'] = gettext('Source')
        info['os_logo'] = 'source-logo.png'
      elif asset['content_type'] == 'application/x-ms-dos-executable':
        info['os'] = 'windows'
        info['display_os'] = 'Windows'
        info['short_os'] = 'Windows'
        info['os_logo'] = 'windows-logo.png'
        info['arch'] = 32
      elif asset['content_type'] == 'application/x-deb' or asset['content_type'] == 'application/vnd.debian.binary-package':
        for n in data.DEBIAN_NAMES:
          if n in asset['name']:
            info['os'] = 'debian'
            info['display_os'] = 'Debian %s' % n.capitalize()
            info['short_os'] = n.capitalize()
            info['os_logo'] = 'squeeze-logo.png'

        for n in data.UBUNTU_NAMES:
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

def find_download(downloads, os, arch=0):
    downloads = [x for x in downloads if x['os'] == os
                                      and x['arch'] == arch
                                      and x['ver'][:3] == data.LATEST_VERSION[:3]]
    if downloads:
      return copy.deepcopy(downloads[0])
    else:
      return None


def _make_page(template_file, language=None, extra_params=None):
    if language is None:
        language = g.language

    root_page = "/"
    if language != 'en':
        root_page = "/%s/" % language

    if extra_params is None:
      extra_params = {}

    downloads = _fetch_release()

    # Add datetime objects to the list of news
    news = copy.deepcopy(data.NEWS)
    for n in news:
      title = n['title']
      content = n['content']
      n['datetime'] = datetime.datetime.fromtimestamp(n['timestamp'])
      n['title'] = gettext(title)
      n['content'] = gettext(content)

    screenshots = copy.deepcopy(data.SCREENSHOTS)
    for s in screenshots:
      for e in s['entries']:
        title = e['title']
        e['title'] = gettext(title)

    # Try to detect the user's OS and architecture
    ua = request.headers.get('User-Agent', '').lower()
    if 'win' in ua:
      best_download = find_download(downloads, 'windows', 32)
    elif 'mac' in ua:
      best_download = find_download(downloads, 'mac', 64)
    elif 'fedora' in ua:
      if '64' in ua:
        best_download = find_download(downloads, 'fedora', 64)
      else:
        best_download = find_download(downloads, 'fedora', 32)
    else:
      best_download = None

    languages = [{'code': x, 'name': data.LANGUAGE_NAMES[x], 'current': x == language} for x in data.LANGUAGES]

    params = {
      'best_download':      best_download,
      'downloads':          downloads,
      'latest_downloads':   [x for x in downloads if x['ver'] == data.LATEST_VERSION],
      'latest_screenshots': screenshots[0]['entries'],
      'latest_version':     data.LATEST_VERSION,
      'news':               news,
      'language':           language,
      'languages':          languages,
      'old_downloads':      [x for x in downloads if x['ver'] != data.LATEST_VERSION],
      'root_page':          root_page,
      'screenshots':        screenshots,
      'is_rtl':             language == 'ar' or language == 'fa' or language == 'he',
    }
    params.update(extra_params)

    return render_template(template_file, **params)

@app.route('/thumbnails/<filename>')
def thumbnail(filename):
    thumbnail_data = cache.get(filename)
    if thumbnail_data is None:
        image_path = os.path.join(app.static_folder, 'screenshots', filename)
        if os.path.exists(image_path):
            with Image.open(image_path) as img:
                img.thumbnail((440, 440))
                img_io = io.BytesIO()
                img.save(img_io, 'PNG')
                img_io.seek(0)
                thumbnail_data = img_io.read()
                cache.set(filename, thumbnail_data)
        else:
            return "Image not found", 404
    return send_file(io.BytesIO(thumbnail_data), mimetype='image/png')

@app.route('/scheduled/trigger-transifex-pull')
def trigger_transifex_pull():
    credentials, project = google.auth.default(
        scopes=['https://www.googleapis.com/auth/cloud-platform'])
    authed_session = google.auth.transport.requests.AuthorizedSession(credentials)

    response = authed_session.post(
        'https://cloudbuild.googleapis.com/v1/projects/clementine-web/triggers/e19d2c38-5478-4282-a475-ee54d6d5363a:run',
        data=json.dumps({
            'projectId': 'clementine-web',
            'repoName': 'github-clementine-player-website',
            'branchName': 'master',
        })
    )
    return jsonify(response.json())

@app.route('/')
def main_page_no_lang():
    return _make_page('main.html')

@app.route('/<language>/')
def main_page(language=None):
    return _make_page('main.html', language)

@app.route('/screenshots')
def screenshots_page_no_lang():
    return _make_page('screenshots.html')

@app.route('/<language>/screenshots')
def screenshots_page(language=None):
    return _make_page('screenshots.html', language)

@app.route('/downloads')
def downloads_page_no_lang():
    return _make_page('downloads.html')

@app.route('/<language>/downloads')
def downloads_page(language=None):
    return _make_page('downloads.html', language)

@app.route('/participate')
def participate_page_no_lang():
    return _make_page('participate.html')

@app.route('/<language>/participate')
def participate_page(language=None):
    return _make_page('participate.html', language)

@app.route('/privacy')
def privacy_page_no_lang():
    return _make_page('privacy.html')

@app.route('/<language>/privacy')
def privacy_page(language=None):
    return _make_page('privacy.html', language)

@app.route('/wiimote')
def wiimote_page():
    return redirect('https://github.com/clementine-player/Clementine/wiki/Wii-Remotes')

if __name__ == '__main__':
    app.run(debug=True)
