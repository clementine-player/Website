from google.appengine.ext import blobstore
from google.appengine.ext import db

class CrashInfo(db.Model):
  # The minidump's key in blobstore
  blob_key = blobstore.BlobReferenceProperty()

  # The time the crash was reported
  time_reported = db.DateTimeProperty(auto_now_add=True)

  # Fields provided by the client
  version    = db.StringProperty()
  qt_version = db.StringProperty()
  exe_md5    = db.StringProperty()
  os         = db.StringProperty()
  os_version = db.StringProperty()

  # This random string is generated when the crash is reported and passed to the
  # processor in the task queue payload.  The processor must pass it back to
  # retreive the raw blob.
  access_token = db.StringProperty()

  # A serialised Crash protobuf.  Set after the crash has been processed.
  serialised_crash_pb = db.BlobProperty()


class Symbols(db.Model):
  # The symbol file is gzipped.
  blob_key    = blobstore.BlobReferenceProperty()
  time_added  = db.DateTimeProperty(auto_now_add=True)
  binary_hash = db.StringProperty(required=True)
  binary_name = db.StringProperty(required=True)
