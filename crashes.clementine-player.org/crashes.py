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
    crash_data = []

    for entity in models.CrashInfo.all():
      processed = bool(entity.serialised_crash_pb)

      crash_data.append([
        entity.time_reported.isoformat(),
        entity.version,
        entity.qt_version,
        entity.os,
        entity.os_version,
        processed,
      ])

    # Populate the template values.
    values = {
      "crash_data": json.dumps(crash_data),
    }

    # Render the template
    template = jinja_environment.get_template('templates/list.html')
    self.response.out.write(template.render(values))


class CrashPage(webapp2.RequestHandler):
  def get(self, crash_id):
    crash_info = models.CrashInfo.get_by_id(int(crash_id))
    if crash_info is None:
      self.error(404)
      return

    crash_pb = crash_pb2.Crash()
    crash_pb.MergeFromString(crash_info.serialised_crash_pb)

    self.response.out.write(str(crash_pb))


app = webapp2.WSGIApplication([
  (r'/crashes', IndexPage),
  (r'/crash/(.*)', CrashPage),
], debug=True)
