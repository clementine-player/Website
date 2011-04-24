from google.appengine.ext import blobstore
from google.appengine.ext import webapp
from google.appengine.ext.webapp import blobstore_handlers
from google.appengine.ext.webapp.util import run_wsgi_app


class GetUploadUrlPage(webapp.RequestHandler):
  def get(self):
    self.redirect(blobstore.create_upload_url('/uploadhandler'))

  def post(self):
    self.response.headers['Location'] = blobstore.create_upload_url('/uploadhandler')
    self.error(307)


class UploadHandlerPage(blobstore_handlers.BlobstoreUploadHandler):
  def post(self):
    self.redirect("/")


application = webapp.WSGIApplication([
  (r'/getuploadurl', GetUploadUrlPage),
  (r'/uploadhandler', UploadHandlerPage),
], debug=True)

def main():
  run_wsgi_app(application)

if __name__ == '__main__':
  main()
