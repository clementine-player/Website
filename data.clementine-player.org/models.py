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


class MacUpdate(ndb.Model):
  """An update in the Sparkle 2 feed, /sparkle2: a macOS build from
  Clementine's master, published by its tools/mac-update. Keyed by build.

  The feed takes the most recently published one for each minimum macOS,
  which tools/mac-update keeps the highest build for it.

  Builds from before Sparkle 2 check /sparkle, which serves Version
  entities instead."""

  version = ndb.StringProperty(required=True, indexed=False)  # what people see
  build = ndb.StringProperty(required=True, indexed=False)  # what Sparkle compares
  min_macos = ndb.StringProperty(required=True)
  download_url = ndb.StringProperty(required=True, indexed=False)
  ed_signature = ndb.StringProperty(required=True, indexed=False)  # base64
  length = ndb.IntegerProperty(required=True, indexed=False)  # the DMG's, in bytes
  notes = ndb.StringProperty(repeated=True, indexed=False)  # for users, one each
  published = ndb.DateTimeProperty(required=True)


class Counter(ndb.Model):
  count = ndb.IntegerProperty(indexed=False, required=True)


class CounterSnapshot(ndb.Model):
  counter = ndb.KeyProperty(kind='Counter', required=True)
  count = ndb.IntegerProperty(indexed=False, required=True)
  date = ndb.DateProperty(auto_now_add=True)
