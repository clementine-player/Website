"""Minimal in-memory fake of google.cloud.datastore for CI smoke testing.

The real client talks to a live GCP project, which CI doesn't have
credentials for (and shouldn't need, just to prove the app boots and its
routes render). Put this directory ahead of site-packages on PYTHONPATH to
use it instead of the real google-cloud-datastore package.
"""


class Key(object):
  def __init__(self, kind, name):
    self.kind = kind
    self.name = name

  def __hash__(self):
    return hash((self.kind, self.name))

  def __eq__(self, other):
    return isinstance(other, Key) and (self.kind, self.name) == (other.kind, other.name)


class Entity(dict):
  def __init__(self, key, exclude_from_indexes=()):
    super(Entity, self).__init__()
    self.key = key
    self.exclude_from_indexes = exclude_from_indexes


_STORE = {}

# Real Datastore limit: indexed string/bytes properties can't exceed 1500
# bytes. Enforced here too, so a property that should be excluded from
# indexing but isn't gets caught locally instead of only in production.
MAX_INDEXED_PROPERTY_BYTES = 1500


class Client(object):
  def key(self, kind, name):
    return Key(kind, name)

  def get(self, key):
    return _STORE.get((key.kind, key.name))

  def put(self, entity):
    for prop_name, prop_value in entity.items():
      if prop_name in entity.exclude_from_indexes:
        continue
      if isinstance(prop_value, (str, bytes)) and len(prop_value) > MAX_INDEXED_PROPERTY_BYTES:
        raise ValueError(
            'InvalidArgument: The value of property "%s" is longer than %d bytes.'
            % (prop_name, MAX_INDEXED_PROPERTY_BYTES))
    _STORE[(entity.key.kind, entity.key.name)] = entity
