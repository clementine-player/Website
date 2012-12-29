import jinja2
import json
import os
import webapp2

import crash_pb2
import models

jinja_environment = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)))


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
    }

    # Render the template
    template = jinja_environment.get_template('templates/crash.html')
    self.response.out.write(template.render(values))


app = webapp2.WSGIApplication([
  (r'/', IndexPage),
  (r'/crash/(.*)', CrashPage),
], debug=True)
