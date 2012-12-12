import webapp2

class SkydrivePage(webapp2.RequestHandler):
  def get(self):
    port = self.request.get('port')
    code = self.request.get('code')
    url = 'http://localhost:%s/?code=%s' % (port, code)
    self.redirect(str(url))

app = webapp2.WSGIApplication(
    [
        (r'/skydrive', SkydrivePage)
    ],
    debug=True)
