from google.appengine.ext import blobstore
from google.appengine.ext import db

class CrashGroup(db.Model):
  # A reference to the issue on codesite.
  issue_id = db.IntegerProperty()
  issue_summary = db.StringProperty()


class CrashInfo(db.Model):
  # Cloud Storage paths for the actual data.
  minidump_gs_read_path = db.StringProperty()
  log_gs_read_path      = db.StringProperty()

  # The time the crash was reported
  time_reported = db.DateTimeProperty(auto_now_add=True)

  # Fields provided by the client
  version    = db.StringProperty()
  qt_version = db.StringProperty()
  os         = db.StringProperty()
  os_version = db.StringProperty()

  # On Linux we get the whole of /etc/lsb-release in os_version.  Try to shorten
  # it a bit for this field.
  short_os_version = db.StringProperty()

  # A serialised Crash protobuf.  Set after the crash has been processed.
  serialised_crash_pb = db.BlobProperty()

  # Multiple crashes can be grouped together.
  crash_group = db.ReferenceProperty(CrashGroup)


class Symbols(db.Model):
  # The symbol file is gzipped.
  time_added  = db.DateTimeProperty(auto_now_add=True)
  binary_hash = db.StringProperty(required=True)
  binary_name = db.StringProperty(required=True)

  # The path to the data in Cloud Storage.
  gs_read_path = db.StringProperty(required=True)
