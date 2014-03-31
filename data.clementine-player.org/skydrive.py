import webapp2

class SkydrivePage(webapp2.RequestHandler):
  def get(self):
    port = self.request.get('port')
    if not port:
      # SoundCloud forces us to have a fixed URL (i.e. without the port parameter)
      # However, we can have a 'state' param, which will be append to the
      # redirect URI
      port = self.request.get('state')
    code = self.request.get('code')
    url = 'http://localhost:%s/?code=%s' % (port, code)
    self.redirect(str(url))

app = webapp2.WSGIApplication(
    [
        (r'/skydrive', SkydrivePage)
    ],
    debug=True)
