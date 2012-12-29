from google.appengine.api import taskqueue
from google.appengine.ext import blobstore
from google.appengine.ext import db
from google.appengine.ext.webapp import blobstore_handlers

import base64
import functools
import googlepb.protobuf.message
import logging
import webapp2

import crash_pb2
import models
import utils

AUTHORIZATION_PREFIX = "Token "


def CheckAccessToken(func):
  @functools.wraps(func)
  def Wrapper(self, key):
    # The access token is passed in the Authorization header.  This token is
    # only sent in the task queue payload, so if the client has it, it must have
    # authenticated with the task queue API already.
    auth = self.request.headers["authorization"]
    if not auth.startswith(AUTHORIZATION_PREFIX):
      self.error(401)
      return

    token = auth[len(AUTHORIZATION_PREFIX):]

    # Get the entity.
    crash_info = models.CrashInfo.get(key)
    if crash_info is None:
      self.error(404)
      return

    # Check the token matches.
    if crash_info.access_token != token:
      self.error(401)
      return

    return func(self, crash_info)
  return Wrapper


class RawCrashDownloadPage(utils.ExceptionHandlerMixin,
                           blobstore_handlers.BlobstoreDownloadHandler):
  @CheckAccessToken
  def get(self, crash_info):
    self.send_blob(crash_info.blob_key)


class ProcessCrashPage(utils.ExceptionHandlerMixin, webapp2.RequestHandler):
  @CheckAccessToken
  def post(self, crash_info):
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

    # Delete the task.
    logging.info("Deleting task with ID '%s'", task_id)
    try:
      taskqueue.Queue("raw-crashes").delete_tasks(taskqueue.Task(name=task_id))
    except Exception:
      logging.exception("Failed to delete task with ID '%s'", task_id)

    # Delete the blob.
    logging.info("Deleting blob with key '%s'", str(crash_info.blob_key))
    try:
      crash_info.delete()
    except Exception:
      logging.exception("Failed to delete blob with key '%s'",
                         str(crash_info.blob_key))

    # Update the crash.
    crash_info.serialised_crash_pb = serialised_crash_pb
    crash_info.put()


app = webapp2.WSGIApplication([
  (r'/rawcrash/(.*)', RawCrashDownloadPage),
  (r'/processcrash/(.*)', ProcessCrashPage),
], debug=True)
