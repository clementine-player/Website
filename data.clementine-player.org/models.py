from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.ext import ndb

class GoogleCode(db.Model):
  name = db.StringProperty(required=True)
  secret = db.StringProperty(required=True)


class Follower(db.Model):
  user = db.UserProperty(required=True)
  project = db.ReferenceProperty(GoogleCode, collection_name='followers')


class Version(db.Model):
  platform = db.StringProperty()
  revision = db.StringProperty()
  version = db.StringProperty(required=True)

  download_link = db.LinkProperty(required=True)
  signature = db.StringProperty()  # Base64 encoded
  bundle_size = db.IntegerProperty()

  # Use either changelog_link or changelog.
  changelog_link = db.LinkProperty()
  changelog = db.TextProperty()  # This can be unescaped HTML.

  publish_date = db.DateTimeProperty(auto_now_add=True)

  min_version = db.StringProperty()

  tags = db.StringListProperty()


class Device(db.Model):
  registration_id = db.StringProperty(required=True)
  user = db.UserProperty(required=True)
  brand = db.StringProperty()
  device = db.StringProperty()
  manufacturer = db.StringProperty()
  model = db.StringProperty()
  serial = db.StringProperty()


class KnownRevision(db.Model):
  project_name = db.StringProperty()
  sha1 = db.StringProperty()


class OAuthToken(ndb.Model):
  purpose = ndb.StringProperty(required=True)
  token = ndb.StringProperty(required=True)
  updated = ndb.DateTimeProperty(auto_now=True)
