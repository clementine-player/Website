import base64
import time
import logging
import urllib

import Crypto.Hash.SHA256 as SHA256
import Crypto.PublicKey.RSA as RSA
import Crypto.Signature.PKCS1_v1_5 as PKCS1_v1_5

import service_account_secrets

DEFAULT_SIGNED_URL_EXPIRATION_SECS = 15 * 60  # 15 minutes


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


def SignedUrlParams(resource, verb, expiration, content_type):
  expiration = str(int(expiration))

  # Generate the signature
  string_to_sign = '\n'.join([
    verb,
    '',  # Content-MD5
    content_type,
    expiration,
    resource,
  ])

  key = RSA.importKey(service_account_secrets.CLIENT_PRIVATE_KEY)
  shahash = SHA256.new(string_to_sign)
  signer = PKCS1_v1_5.new(key)
  signature_bytes = signer.sign(shahash)
  signature_b64 = base64.b64encode(signature_bytes)

  return {
    'GoogleAccessId': service_account_secrets.CLIENT_ID_EMAIL,
    'Expires': expiration,
    'Signature': signature_b64,
  }


def MakeSignedUrl(resource, verb='PUT', expiration=None,
                  content_type='application/gzip'):
  if expiration is None:
    expiration = time.time() + DEFAULT_SIGNED_URL_EXPIRATION_SECS

  params = SignedUrlParams(resource, verb, expiration, content_type)
  return 'https://storage.googleapis.com%s?%s' % (
      resource, urllib.urlencode(params))
