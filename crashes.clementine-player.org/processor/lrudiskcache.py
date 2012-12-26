import collections
import errno
import os

DEFAULT_MAX_SIZE = 500 * (10 ** 20) # 500 MB

class LRUDiskCache(object):
  def __init__(self, directory, max_size=DEFAULT_MAX_SIZE):
    self.directory = directory
    self.max_size = max_size

    self._data = {}
    self._queue = collections.deque()
    self._refcount = collections.Counter()
    self.total_size = 0

    # Read keys that already exist in the cache.
    for root, dirs, files in os.walk(directory):
      for filename in files:
        path = os.path.join(root, filename)
        key = os.path.relpath(path, directory)
        size = os.path.getsize(path)

        self._Insert(key, size)

  def Contains(self, key):
    if key not in self._data:
      return False

    self._queue.appendleft(key)
    self._refcount[key] += 1
    return True

  def _Insert(self, key, size):
    if key in self._data:
      raise KeyError(key)

    # Insert this item
    self._data[key] = size
    self._queue.appendleft(key)
    self._refcount[key] += 1
    self.total_size += size

    # Cleanup old items if the cache is too big now
    while self.total_size > self.max_size:
      while True:
        key = self._queue.pop()
        self._refcount[key] -= 1
        if self._refcount[key] == 0:
          self._RemoveFile(key)
          self.total_size -= self._data[key]
          del self._data[key], self._refcount[key]
          break

  def _Path(self, key):
    return os.path.join(self.directory, key)

  def _RemoveFile(self, key):
    os.unlink(self._Path(key))

  def OpenExistingFile(self, key):
    if not self.Contains(key):
      raise KeyError(key)

    return open(self._Path(key))

  def WriteFile(self, key, data):
    # Make room on disk.
    self._Insert(key, len(data))

    path = self._Path(key)

    # Create parent directories.
    try:
      os.makedirs(os.path.dirname(path))
    except OSError, ex:
      # It's fine if the directory already exists.
      if ex.errno != errno.EEXIST:
        raise

    # Create the file.
    with open(path, "w") as handle:
      handle.write(data)
