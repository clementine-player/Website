import base64
import jinja2
import logging
import os
import sys
import uuid
import webapp2

from google.appengine.api import channel

import google
vendor_dir = os.path.join(os.path.dirname(__file__), 'vendor')
google.__path__.append(os.path.join(vendor_dir, 'google'))
sys.path.insert(0, vendor_dir)
import remotecontrolmessages_pb2


class ChannelPage(webapp2.RequestHandler):
  def get(self):
    id = str(uuid.uuid4())
    token = channel.create_channel(id)
    print id
    template = jinja_environment.get_template('channel.html')
    self.response.out.write(template.render({'token': token}))


class TestPage(webapp2.RequestHandler):
  def get(self):
    id = self.request.get('id')
    channel.send_message(id, 'Hello World')


class ChannelConnectedPage(webapp2.RequestHandler):
  def post(self):
    client_id = self.request.get('from')
    print client_id
    message = remotecontrolmessages_pb2.Message()
    message.version = 14
    message.type = remotecontrolmessages_pb2.CONNECT
    message.request_connect.send_playlist_songs = True
    binary = message.SerializeToString()
    string = base64.b64encode(binary)
    print string
    channel.send_message(client_id, string)


class ChannelDisconnectedPage(webapp2.RequestHandler):
  def post(self):
    pass


jinja_environment = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)))
app = webapp2.WSGIApplication(
    [
        ('/channel', ChannelPage),
        ('/channel_test.*', TestPage),
        ('/_ah/channel/connected/', ChannelConnectedPage),
        ('/_ah/channel/disconnected/', ChannelDisconnectedPage),
    ],
    debug=True)
