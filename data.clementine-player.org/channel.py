import base64
import jinja2
import json
import logging
import os
import sys
import uuid
import webapp2

from google.appengine.api import channel
from google.appengine.ext import ndb

import google
vendor_dir = os.path.join(os.path.dirname(__file__), 'vendor')
google.__path__.append(os.path.join(vendor_dir, 'google'))
sys.path.insert(0, vendor_dir)
import remotecontrolmessages_pb2


class RemoteInstance(ndb.Model):
  # id string uuid
  created = ndb.DateTimeProperty(auto_now_add=True)
  updated = ndb.DateTimeProperty(auto_now=True)
  channels = ndb.JsonProperty()


"""Page rendered for a clementine instance."""
class ChannelPage(webapp2.RequestHandler):
  def get(self):
    id = str(uuid.uuid4())
    token = channel.create_channel(id)
    remote_instance = RemoteInstance(id=id)
    remote_instance.put()
    template = jinja_environment.get_template('channel.html')
    self.response.out.write(template.render({
        'token': token,
        'id': id,
    }))


"""Page rendered for the actual web remote."""
class RemotePage(webapp2.RequestHandler):
  def get(self, clementine_instance_id):
    id = str(uuid.uuid4())
    token = channel.create_channel(id)
    instance = RemoteInstance.get_by_id(clementine_instance_id)
    if instance is None:
      self.error(404)
      logging.error('Tried to connect to non-existant instance')
      return
    channels = instance.channels or []
    channels.append(id)
    instance.channels = channels
    instance.put()
    template = jinja_environment.get_template('remote.html')
    self.response.out.write(template.render({
        'token': token,
        'id': clementine_instance_id,
    }))


"""Page for Clementine instances to push remote control messages to."""
class ClementinePushPage(webapp2.RequestHandler):
  def post(self, id):
    instance = RemoteInstance.get_by_id(id)
    if instance is None:
      self.error(403)
      logging.error('Tried to push message to non-existant instance')
      return

    message = remotecontrolmessages_pb2.Message()
    message.ParseFromString(base64.b64decode(self.request.body))
    logging.debug(message)

    for chan in instance.channels:
      channel.send_message(chan, self.request.body)


"""Page for Remote instances to push remote control messages to."""
class RemotePushPage(webapp2.RequestHandler):
  def post(self, id):
    instance = RemoteInstance.get_by_id(id)
    if instance is None:
      self.error(403)
      logging.error('Clementine instance has gone')

    req = json.loads(self.request.body)
    message = remotecontrolmessages_pb2.Message()
    message.version = 14

    if req['method'] == 'ping':
      message.type = remotecontrolmessages_pb2.KEEP_ALIVE
    elif req['method'] == 'playpause':
      message.type = remotecontrolmessages_pb2.PLAYPAUSE

    binary = message.SerializeToString()
    string = base64.b64encode(binary)
    channel.send_message(id, string)


class TestPage(webapp2.RequestHandler):
  def get(self):
    id = self.request.get('id')
    channel.send_message(id, 'Hello World')


class ChannelConnectedPage(webapp2.RequestHandler):
  def post(self):
    client_id = self.request.get('from')
    message = remotecontrolmessages_pb2.Message()
    message.version = 14
    message.type = remotecontrolmessages_pb2.CONNECT
    message.request_connect.send_playlist_songs = True
    binary = message.SerializeToString()
    string = base64.b64encode(binary)
    channel.send_message(client_id, string)


class ChannelDisconnectedPage(webapp2.RequestHandler):
  def post(self):
    pass



jinja_environment = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)))
app = webapp2.WSGIApplication(
    [
        (r'/channel/clementine/push/(.*)', ClementinePushPage),
        (r'/channel/clementine', ChannelPage),
        (r'/channel/remote/push/(.*)', RemotePushPage),
        (r'/channel/remote/(.*)', RemotePage),

        (r'/channel_test.*', TestPage),
        (r'/_ah/channel/connected/', ChannelConnectedPage),
        (r'/_ah/channel/disconnected/', ChannelDisconnectedPage),
    ],
    debug=True)
