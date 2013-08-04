from google.appengine.api import files
from google.appengine.api import users

import datetime
import jinja2
import jinja2.utils
import json
import logging
import os
import re
import webapp2
import xml.sax.saxutils

import crash_pb2
import models

GIT_VERSION_RE = re.compile(r'.*-g([0-9a-f]{7})$')
RELEASED_VERSION_RE = re.compile(r'^(\d+\.\d+(?:\.\d+)?)$')
TOPLEVEL_SOURCE_DIRS = [
    "3rdparty",
    "ext",
    "src",
]
LOG_LINE_RE = re.compile(
    r'^(\d{2}:\d{2}:\d{2}\.\d{3}) ([A-Z]+)(\s+)([^ ]+)(\s+)(.*)$')

CODESITE_URL_BASE = \
    "http://code.google.com/p/clementine-player/source/browse/%%s%s#%%d"

ITEMS_PER_PAGE = 50


jinja_environment = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    autoescape=True)


def CodesiteURLTemplate(version):
  query = ""

  if version:
    match = GIT_VERSION_RE.match(version)
    if match:
      query = "?r=" + match.group(1)
    else:
      match = RELEASED_VERSION_RE.match(version)
      if match:
        query = "?name=" + version

  return CODESITE_URL_BASE % query


def MakeLinkifySource(version):
  url_template = CodesiteURLTemplate(version)
  def LinkifySource(filename, line_number):
    # Get the filename relative to the repository.
    relative_index = None
    for toplevel_dir in TOPLEVEL_SOURCE_DIRS:
      index = filename.rfind("/%s/" % toplevel_dir)
      if index != -1:
        relative_index = index + 1
        break

    if relative_index is None:
      return "%s:%d" % (filename, line_number)

    relative_filename = filename[relative_index:]

    return jinja2.utils.Markup('<a href="%s">%s:%d</a>' % (
      url_template % (relative_filename, line_number),
      xml.sax.saxutils.escape(relative_filename),
      line_number,
    ))
  return LinkifySource


def filesizeformat(value, binary=False):
  """
  The filesizeformat filter in appengine's version of jinja is broken.  This is
  the correct one from latest jinja.
  """
  bytes = float(value)
  base = binary and 1024 or 1000
  prefixes = [
      (binary and 'KiB' or 'kB'),
      (binary and 'MiB' or 'MB'),
      (binary and 'GiB' or 'GB'),
      (binary and 'TiB' or 'TB'),
      (binary and 'PiB' or 'PB'),
      (binary and 'EiB' or 'EB'),
      (binary and 'ZiB' or 'ZB'),
      (binary and 'YiB' or 'YB')
  ]
  if bytes == 1:
    return '1 Byte'
  elif bytes < base:
    return '%d Bytes' % bytes
  else:
    for i, prefix in enumerate(prefixes):
      unit = base ** (i + 2)
      if bytes < unit:
        return '%.1f %s' % ((base * bytes / unit), prefix)
    return '%.1f %s' % ((base * bytes / unit), prefix)
jinja_environment.filters["filesizeformat"] = filesizeformat


def relativedate(value):
  delta = (datetime.datetime.now() - value).total_seconds()

  if delta < 0:
    return "The future"
  if delta < 60:
    return "%d seconds ago" % delta
  if delta < 60 * 60:
    return "%d minutes ago" % (delta / 60)
  if delta < 60 * 60 * 24:
    return "%d hours ago" % (delta / (60 * 60))
  return "%d days ago" % (delta / (60 * 60 * 24))
jinja_environment.filters["relativedate"] = relativedate


def FormatLogText(text):
  html_lines = []

  for line in text.splitlines():
    match = LOG_LINE_RE.match(line)
    if not match:
      html_lines.append(xml.sax.saxutils.escape(line))
      continue

    date, level, space1, origin, space2, text = match.groups()

    html_lines.append(
        '<span class="logline-%s">'
            '<span class="date">%s </span>'
            '<span class="level">%s%s</span>'
            '<span class="origin">%s%s</span>'
            '<span class="text">%s</span>'
        '</span>' % (
            xml.sax.saxutils.escape(level),
            xml.sax.saxutils.escape(date),
            xml.sax.saxutils.escape(level), space1,
            xml.sax.saxutils.escape(origin), space2,
            xml.sax.saxutils.escape(text),
        )
    )

  return jinja2.utils.Markup("\n".join(html_lines))
jinja_environment.filters["FormatLogText"] = FormatLogText


class BasePage(webapp2.RequestHandler):
  def Render(self, template_filename, values):
    new_values = {
      "user": users.get_current_user(),
      "user_is_admin": users.is_current_user_admin(),
      "login_url": users.create_login_url(self.request.url),
      "logout_url": users.create_logout_url(self.request.url),
    }
    new_values.update(values)

    # Render the template
    template = jinja_environment.get_template(template_filename)
    self.response.out.write(template.render(new_values))


class IndexPage(BasePage):
  def get(self):
    offset = int(self.request.get('offset', 0))

    # Get the data
    query = models.CrashInfo.all()
    query.order('-time_reported')
    crashes = query.fetch(ITEMS_PER_PAGE, offset=offset)

    # Should we display next/previous links?
    has_previous = offset > 0
    has_next = (
        len(crashes) == ITEMS_PER_PAGE and
        query.count(offset=offset, limit=ITEMS_PER_PAGE+1) > ITEMS_PER_PAGE)

    previous_url = "%s?offset=%d" % (
        self.request.path, max(0, offset - ITEMS_PER_PAGE))
    next_url = "%s?offset=%d" % (self.request.path, offset + ITEMS_PER_PAGE)

    # Render the template
    self.Render('templates/list.html', {
      "crashes": crashes,
      "has_previous": has_previous,
      "has_next": has_next,
      "previous_url": previous_url,
      "next_url": next_url,
    })


class CrashPage(BasePage):
  def get(self, crash_id):
    # Get the data.
    crash_info = models.CrashInfo.get_by_id(int(crash_id))
    if crash_info is None:
      self.error(404)
      return

    # Parse the protobuf.
    crash_pb = None
    if crash_info.serialised_crash_pb:
      crash_pb = crash_pb2.Crash()
      crash_pb.MergeFromString(crash_info.serialised_crash_pb)

    # Get the log text if the user is an administrator.
    log_text = None
    log_error = None
    has_log_file = False
    if crash_info.log_gs_read_path:
      has_log_file = True
      if users.is_current_user_admin():
        try:
          # Read only the first 1MB of the log.
          with files.open('/gs' + crash_info.log_gs_read_path, 'r') as handle:
            log_text = handle.read(2 ** 20)
        except files.Error as ex:
          log_error = str(ex)

    # Render the template
    self.Render('templates/crash.html', {
      "hostname": self.request.headers["host"],
      "info": crash_info,
      "crash_pb": crash_pb,
      "log_text": log_text,
      "log_error": log_error,
      "has_log_file": has_log_file,
      "LinkifySource": MakeLinkifySource(crash_info.version),
    })


app = webapp2.WSGIApplication([
  (r'/', IndexPage),
  (r'/crash/(.*)', CrashPage),
], debug=True)
