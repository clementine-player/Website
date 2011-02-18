import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'settings'
from google.appengine.dist import use_library
use_library('django', '1.2')

from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app

from django.utils import simplejson

import logging
import os

import models


class RegisterDevice(webapp.RequestHandler):
  def post(self):
    user = users.get_current_user()
    registration_id = self.request.get('registration_id')
    brand = self.request.get('brand')
    device = self.request.get('device')
    manufacturer = self.request.get('manufacturer')
    model = self.request.get('model')
    serial = self.request.get('serial')

    if registration_id is None:
      self.response.out.write('No registration id')
      self.error(400)
      return

    d = models.Device(
        registration_id=registration_id,
        user=user,
        brand=brand,
        device=device,
        manufacturer=manufacturer,
        model=model,
        serial=serial)
    d.put()
    self.response.out.write('OK')


class ListDevices(webapp.RequestHandler):
  def get(self):
    user = users.get_current_user()
    query = models.Device.gql('WHERE user = :user', user=user)
    devices = query.fetch(10)
    path = os.path.join(os.path.dirname(__file__), 'devices.html')
    self.response.out.write(template.render(path, {'devices': devices}))


application = webapp.WSGIApplication(
    [
        (r'/c2dm/register', RegisterDevice),
        (r'/c2dm/list', ListDevices),
    ],
    debug=True)

def main():
  run_wsgi_app(application)

if __name__ == '__main__':
  main()
