from google.appengine.ext import db

import json
import logging
import re
import webapp2

import models
import utils


class SymbolUploadUrls(utils.ExceptionHandlerMixin, webapp2.RequestHandler):
  SYMBOL_RE = re.compile(r'^([a-zA-Z0-9_.+-]+)/([A-F0-9]+)$')
  BUCKET_NAME = 'clementine_crashes_symbols'

  def post(self):
    urls = {}
    records = []

    for symbol in self.request.get_all('symbol'):
      match = self.SYMBOL_RE.match(symbol)
      if not match:
        raise utils.BadRequest('Invalid symbol name %s', symbol)

      binary_name = match.group(1)
      binary_hash = match.group(2)
      gs_path = '/%s/%s' % (self.BUCKET_NAME, symbol)

      # Check whether this symbol file has been uploaded already.
      query = models.Symbols.all(keys_only=True)
      query.filter("binary_name =", binary_name)
      query.filter("binary_hash =", binary_hash)
      if query.get() is not None:
        logging.info('Skipping existing symbol %s/%s' % (
            binary_name, binary_hash))
        continue

      logging.info('Making signed URL for %s/%s' % (binary_name, binary_hash))

      # Make a signed URL for this object.
      urls[symbol] = utils.MakeSignedUrl(gs_path)

      # Create a new datastore record.
      records.append(models.Symbols(
          binary_hash=binary_hash,
          binary_name=binary_name,
          gs_read_path=gs_path))

    # Put all the records in the datastore.
    db.put(records)

    # JSON encode the response.
    json.dump({
      "urls": urls,
    }, self.response.out)


app = webapp2.WSGIApplication([
  (r'/api/upload/symbols', SymbolUploadUrls),
], debug=True)
