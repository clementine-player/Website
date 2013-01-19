from google.appengine.api import taskqueue
from google.appengine.ext import db

import base64
import logging
import json
import re
import time
import webapp2

import googlepb.protobuf.message

import crash_pb2
import models
import utils


ALLOWED_CRASH_ARGUMENTS = [
  "version",
  "qt_version",
  "os",
  "os_version",
]

LINUX_OS_VERSION_RE = re.compile(r'([A-Z_]+)=(?:([\w]+)|"([^"]+)")')
MINIDUMP_GS_READ_PATH = '/clementine_crashes_minidumps/%d'
LOG_GS_READ_PATH = '/clementine_crashes_logs/%d'


class MinidumpUploadUrl(utils.ExceptionHandlerMixin, webapp2.RequestHandler):
  def ShortenOSVersion(self, os_version):
    fields = {
        key: unquoted_value or quoted_value
        for (key, unquoted_value, quoted_value)
        in LINUX_OS_VERSION_RE.findall(os_version)
    }

    if "DISTRIB_DESCRIPTION" in fields:
      return fields["DISTRIB_DESCRIPTION"]

    if "DISTRIB_ID" in fields:
      if "DISTRIB_RELEASE" in fields:
        return "%s %s" % (fields["DISTRIB_ID"], fields["DISTRIB_RELEASE"])
      return fields["DISTRIB_ID"]

    return os_version

  def post(self):
    # Create a datastore record for the crash.
    crash_info = models.CrashInfo()
    crash_info.put()

    # Use the record's new key in the Cloud Storage paths.
    key = crash_info.key().id()

    try:
      crash_info.minidump_gs_read_path = MINIDUMP_GS_READ_PATH % key
      crash_info.log_gs_read_path = LOG_GS_READ_PATH % key

      # Make signed URLs for the minidump and the log.
      minidump_url = utils.MakeSignedUrl(
          crash_info.minidump_gs_read_path, content_type='application/octet-stream')
      log_url = utils.MakeSignedUrl(
          crash_info.log_gs_read_path, content_type='text/plain')

      # If the client provided any query arguments then set those on the
      # datastore entry too.
      for arg in ALLOWED_CRASH_ARGUMENTS:
        value = self.request.get(arg, default_value=None)
        if value is not None:
          setattr(crash_info, arg, value)

      if crash_info.os_version:
        crash_info.os_version = self.ShortenOSVersion(crash_info.os_version)

      # Add the crash report to the task queue.
      task_payload = {
        "key": str(key),
      }

      taskqueue.Queue("raw-crashes").add([
          taskqueue.Task(method="PULL", payload=json.dumps(task_payload)),
      ])

      # Return the signed URLs so the client can upload the actual data.
      # Deliberately don't use JSON or anything complicated here to make things
      # easier for the client.
      self.response.out.write('%s\n%s\n' % (minidump_url, log_url))

    except Exception:
      crash_info.delete()
      raise
    else:
      crash_info.put()


class CrashReportUploadHandler(
    utils.ExceptionHandlerMixin, webapp2.RequestHandler):
  def post(self):
    crash_key = int(self.request.get("crash_key"))
    if not crash_key:
      raise utils.BadRequest("Missing required parameter 'crash_key'")

    serialised_crash_pb_b64 = self.request.get("crash_pb_b64")
    if not serialised_crash_pb_b64:
      raise utils.BadRequest("Missing required parameter 'crash_pb_b64'")

    try:
      serialised_crash_pb = base64.b64decode(serialised_crash_pb_b64)
    except TypeError:
      raise utils.BadRequest("Invalid base64 'crash_pb_b64'")

    task_id = self.request.get("task_id")
    if not task_id:
      raise utils.BadRequest("Missing required parameter 'task_id'")

    # Try parsing the protobuf to check it's valid.
    try:
      crash_pb2.Crash().MergeFromString(serialised_crash_pb)
    except googlepb.protobuf.message.DecodeError, ex:
      raise utils.BadRequest("Error decoding crash_pb: %s" % str(ex))

    # Try getting the crash report from datastore.
    crash_info = models.CrashInfo.get_by_id(crash_key)
    if crash_info is None:
      raise utils.BadRequest("Unknown crash key: %d" % crash_key)

    # Delete the task.
    logging.info("Deleting task with ID '%s'", task_id)
    try:
      taskqueue.Queue("raw-crashes").delete_tasks(taskqueue.Task(name=task_id))
    except Exception:
      logging.exception("Failed to delete task with ID '%s'", task_id)

    # Update the crash.
    crash_info.serialised_crash_pb = serialised_crash_pb
    crash_info.put()


app = webapp2.WSGIApplication([
  (r'/api/upload/minidump', MinidumpUploadUrl),
  (r'/api/upload/crashreport', CrashReportUploadHandler),
], debug=True)
