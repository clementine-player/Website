import webapp2


class IndexPage(webapp2.RequestHandler):
  def get(self):
    self.redirect("http://www.clementine-player.org/")


app = webapp2.WSGIApplication([
  (r'/.*', IndexPage),
], debug=True)
