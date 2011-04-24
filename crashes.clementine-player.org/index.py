from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app


class IndexPage(webapp.RequestHandler):
  def get(self):
    self.redirect("http://www.clementine-player.org/")


application = webapp.WSGIApplication([
  (r'/.*', IndexPage),
], debug=True)

def main():
  run_wsgi_app(application)

if __name__ == '__main__':
  main()
