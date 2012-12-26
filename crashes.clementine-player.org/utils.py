import functools
import logging


class BadRequest(Exception):
  """ExceptionHandlerMixin will catch this and return an HTTP 400."""


class ExceptionHandlerMixin(object):
  """Catches BadRequest exceptions and returns HTTP 400s."""

  def handle_exception(self, exception, debug_mode):
    if not isinstance(exception, BadRequest):
      super(ExceptionHandlerMixin, self).handle_exception(exception, debug_mode)
      return

    self.response.clear()
    self.response.set_status(400)
    self.response.out.write(str(exception))

    logging.warning("Bad request raised by handler: %s", exception)


def CheckAllowedUploadType(allowed_types):
  def Decorator(func):
    @functools.wraps(func)
    def Wrapper(self, request_type):
      if request_type not in allowed_types:
        raise BadRequest(
            "Bad upload type (expected one of %s)" % allowed_types)

      return func(self, request_type)
    return Wrapper
  return Decorator


class FragileBlob(object):
  """Context manager that deletes the blob if an exception occurs."""

  def __init__(self, blob):
    self.blob = blob

  def __enter__(self):
    pass

  def __exit__(self, exc_type, exc_value, traceback):
    if exc_type is not None:
      logging.info("Deleting blob '%s' after exception in handler",
                   self.blob.key())
      self.blob.delete()
