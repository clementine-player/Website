from google.appengine.ext import blobstore
from google.appengine.ext import db
from google.appengine.ext.webapp import blobstore_handlers

import json
import urllib
import webapp2

import models
import utils


class SymbolCheckPage(utils.ExceptionHandlerMixin, webapp2.RequestHandler):
  def post(self):
    # The request is a JSON object
    request = json.load(self.request.body_file)

    # The response will be a list of the symbols we have and don't have.
    present_symbols = []
    missing_symbols = []

    for binary_info in request["binary_info"]:
      query = models.Symbols.all(keys_only=True)
      query.filter("binary_name =", binary_info["name"])
      query.filter("binary_hash =", binary_info["hash"])
      if query.get() is None:
        missing_symbols.append(binary_info)
      else:
        present_symbols.append(binary_info)

    json.dump({
      "present_symbols": present_symbols,
      "missing_symbols": missing_symbols,
    }, self.response.out)


class SymbolDownloadPage(utils.ExceptionHandlerMixin,
                         blobstore_handlers.BlobstoreDownloadHandler):
  def get(self, binary_name, binary_hash):
    binary_name = urllib.unquote(binary_name)
    binary_hash = urllib.unquote(binary_hash)

    query = models.Symbols.all()
    query.filter("binary_name =", binary_name)
    query.filter("binary_hash =", binary_hash)

    entity = query.get()
    if entity is None:
      self.error(404)
      return

    self.send_blob(entity.blob_key, save_as="%s.sym.gz" % binary_name)


app = webapp2.WSGIApplication([
  (r'/symbolcheck', SymbolCheckPage),
  (r'/symbols/(.*)/(.*)', SymbolDownloadPage),
], debug=True)
