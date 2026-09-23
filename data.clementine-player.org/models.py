# -*- coding: utf-8 -*-

from google.cloud import ndb


class Version(ndb.Model):
  platform = ndb.StringProperty()
  revision = ndb.StringProperty()
  version = ndb.StringProperty(required=True)

  download_link = ndb.StringProperty(required=True)
  signature = ndb.StringProperty()  # Base64 encoded
  bundle_size = ndb.IntegerProperty()

  # Use either changelog_link or changelog.
  changelog_link = ndb.StringProperty()
  changelog = ndb.TextProperty()  # This can be unescaped HTML.

  publish_date = ndb.DateTimeProperty(auto_now_add=True)

  min_version = ndb.StringProperty()


class Counter(ndb.Model):
  count = ndb.IntegerProperty(indexed=False, required=True)


class CounterSnapshot(ndb.Model):
  counter = ndb.KeyProperty(kind='Counter', required=True)
  count = ndb.IntegerProperty(indexed=False, required=True)
  date = ndb.DateProperty(auto_now_add=True)
