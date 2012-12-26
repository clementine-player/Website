from google.appengine.api import taskqueue
from google.appengine.ext import blobstore
from google.appengine.ext import db
from google.appengine.ext.webapp import blobstore_handlers

import json
import logging
import random
import string
import urllib
import webapp2

import models
import utils


ALLOWED_UPLOAD_TYPES = {
  "crash",
  "symbols",
}

ALLOWED_CRASH_ARGUMENTS = [
  "version",
  "qt_version",
  "exe_md5",
  "os",
  "os_version",
]

ACCESS_TOKEN_LENGTH = 64
ACCESS_TOKEN_ALPHABET = string.ascii_letters + string.digits


class DeprecatedPage(webapp2.RequestHandler):
  def get(self):
    self.error(410)

  post = get


class GetUploadUrlPage(utils.ExceptionHandlerMixin, webapp2.RequestHandler):
  def BlobstoreUploadUrl(self, request_type):
    return blobstore.create_upload_url('/_uploadhandler/%s' % request_type)

  @utils.CheckAllowedUploadType(ALLOWED_UPLOAD_TYPES)
  def get(self, request_type):
    self.redirect(self.BlobstoreUploadUrl(request_type))

  @utils.CheckAllowedUploadType(ALLOWED_UPLOAD_TYPES)
  def post(self, request_type):
    self.response.headers['Location'] = self.BlobstoreUploadUrl(request_type)
    self.error(307)


class UploadHandlerPage(utils.ExceptionHandlerMixin,
                        blobstore_handlers.BlobstoreUploadHandler):
  @utils.CheckAllowedUploadType(ALLOWED_UPLOAD_TYPES)
  def post(self, request_type):
    function_name = "Handle%s%s" % (request_type[0].upper(),
                                    request_type[1:])
    getattr(self, function_name)()

  def CreateRandomAccessToken(self):
    return ''.join(random.choice(ACCESS_TOKEN_ALPHABET)
                   for _ in xrange(ACCESS_TOKEN_LENGTH))

  def HandleCrash(self):
    blob = self.get_uploads()[0]
    with utils.FragileBlob(blob):
      crash_info = models.CrashInfo(blob_key=blob.key())

      # If the client provided any query arguments then set those on the datastore
      # entry too.
      for arg in ALLOWED_CRASH_ARGUMENTS:
        value = self.request.get(arg, default_value=None)
        if value is not None:
          setattr(crash_info, arg, value)

      # Generate a random access token
      crash_info.access_token = self.CreateRandomAccessToken()

      db.put(crash_info)

    # Add the crash report to the task queue.
    task_payload = {
      "key": str(crash_info.key()),
      "access_token": crash_info.access_token,
    }

    taskqueue.Queue("raw-crashes").add([
        taskqueue.Task(method="PULL", payload=json.dumps(task_payload)),
    ])

  def HandleSymbols(self):
    blob = self.get_uploads()[0]
    with utils.FragileBlob(blob):
      if not blob.filename.endswith(".gz"):
        raise utils.BadRequest(
            "Data should be gzipped and the filename should end with .gz")

      for field in ("name", "hash"):
        if self.request.get(field, default_value=None) is None:
          raise utils.BadRequest("Missing required field '%s'" % field)

      symbol_info = models.Symbols(
          blob_key=blob.key(),
          binary_name=self.request.get("name", default_value=None),
          binary_hash=self.request.get("hash", default_value=None),
      )
      db.put(symbol_info)

    logging.info("Uploaded symbols for %s (%s)" % (
        symbol_info.binary_name, symbol_info.binary_hash))


app = webapp2.WSGIApplication([
  (r'/getuploadurl', DeprecatedPage),
  (r'/upload/(.*)', GetUploadUrlPage),
  (r'/_uploadhandler/(.*)', UploadHandlerPage),
], debug=True)
