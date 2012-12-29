import jinja2
import jinja2.utils
import json
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

CODESITE_URL_BASE = \
    "http://code.google.com/p/clementine-player/source/browse/%%s%s#%%d"


jinja_environment = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    autoescape=True)


def CodesiteURLTemplate(version):
  query = ""

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


class IndexPage(webapp2.RequestHandler):
  def get(self):
    # Get the data
    crashes = list(models.CrashInfo.all())

    # Populate the template values.
    values = {
      "crashes": crashes,
    }

    # Render the template
    template = jinja_environment.get_template('templates/list.html')
    self.response.out.write(template.render(values))


class CrashPage(webapp2.RequestHandler):
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

    # Populate the template values.
    values = {
      "info": crash_info,
      "crash_pb": crash_pb,
      "LinkifySource": MakeLinkifySource(crash_info.version),
    }

    # Render the template
    template = jinja_environment.get_template('templates/crash.html')
    self.response.out.write(template.render(values))


app = webapp2.WSGIApplication([
  (r'/', IndexPage),
  (r'/crash/(.*)', CrashPage),
], debug=True)
