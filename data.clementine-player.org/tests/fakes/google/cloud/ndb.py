"""Minimal in-memory fake of google.cloud.ndb for local smoke testing.

Models the real Cloud NDB API shape (class-level property descriptors that
support `Model.field == value` for building queries, `Model(...).put()`,
`Model.query(...).fetch()`) closely enough to exercise real route code
locally, without needing real GCP credentials.
"""
import datetime
import itertools

_STORE = {}
_next_id = itertools.count(1)


class Client(object):
  def __init__(self, **kwargs):
    pass

  def context(self, **kwargs):
    return _NullContext()


class _NullContext(object):
  def __enter__(self):
    return self

  def __exit__(self, *exc_info):
    return False


class Key(object):
  def __init__(self, kind, id_):
    self.kind_name = kind
    self.id_ = id_

  def id(self):
    return self.id_

  def get(self):
    return _STORE.get((self.kind_name, self.id_))

  def __eq__(self, other):
    return isinstance(other, Key) and (self.kind_name, self.id_) == (other.kind_name, other.id_)

  def __hash__(self):
    return hash((self.kind_name, self.id_))

  def __repr__(self):
    return 'Key(%r, %r)' % (self.kind_name, self.id_)


class _FilterProxy(object):
  """What `Model.field` evaluates to at the class level, so `Model.field ==
  value` (used to build a query) works the same way it does against the
  real client."""

  def __init__(self, name):
    self.name = name

  def __eq__(self, value):
    return (self.name, value)


class Property(object):
  def __init__(self, required=False, default=None, indexed=True,
               auto_now_add=False, auto_now=False, repeated=False, **kwargs):
    self.required = required
    self.default = default
    self.auto_now_add = auto_now_add
    self.auto_now = auto_now
    self.repeated = repeated
    self.name = None

  def __set_name__(self, owner, name):
    self.name = name

  def __get__(self, instance, owner):
    if instance is None:
      return _FilterProxy(self.name)
    return instance._values.get(self.name, [] if self.repeated else self.default)

  def __set__(self, instance, value):
    instance._values[self.name] = value


class StringProperty(Property):
  pass


class TextProperty(Property):
  pass


class IntegerProperty(Property):
  pass


class FloatProperty(Property):
  pass


class DateProperty(Property):
  pass


class DateTimeProperty(Property):
  pass


class KeyProperty(Property):
  def __init__(self, kind=None, **kwargs):
    super(KeyProperty, self).__init__(**kwargs)
    self.kind = kind


class _Query(object):
  def __init__(self, model_cls, filters):
    self.model_cls = model_cls
    self.filters = filters

  def _matches(self, obj):
    for name, value in self.filters:
      if obj._values.get(name) != value:
        return False
    return True

  def fetch(self, limit=None):
    results = [obj for obj in _STORE.values()
               if isinstance(obj, self.model_cls) and self._matches(obj)]
    return results[:limit] if limit else results

  def get(self):
    results = self.fetch(1)
    return results[0] if results else None


class Model(object):
  def __init__(self, id=None, **kwargs):
    self._values = {}
    self.key = Key(type(self).__name__, id) if id is not None else None
    # Real Cloud NDB's DateTimeProperty returns naive datetimes (presumed
    # UTC) unless a tzinfo is explicitly configured -- match that here so
    # anything downstream that's sensitive to naive-vs-aware (e.g. isoformat
    # serialization) sees the same shape it would against the real client.
    now = datetime.datetime.utcnow()
    for name, prop in self._properties().items():
      if prop.auto_now_add or prop.auto_now:
        # DateProperty's real "now" is a date, not a full datetime.
        self._values[name] = now.date() if isinstance(prop, DateProperty) else now
      elif prop.default is not None:
        self._values[name] = prop.default
    for k, v in kwargs.items():
      setattr(self, k, v)

  @classmethod
  def _properties(cls):
    props = {}
    for klass in reversed(cls.__mro__):
      for k, v in vars(klass).items():
        if isinstance(v, Property):
          props[k] = v
    return props

  def put(self):
    if self.key is None:
      self.key = Key(type(self).__name__, next(_next_id))
    _STORE[(self.key.kind_name, self.key.id())] = self
    return self.key

  @classmethod
  def query(cls, *filters):
    return _Query(cls, filters)

  @classmethod
  def get_by_id(cls, id_):
    return _STORE.get((cls.__name__, id_))


def transaction(callback):
  return callback()
