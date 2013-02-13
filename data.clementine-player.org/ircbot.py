# Copyright (c) 2009 Steven Robertson.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 or
# later, as published by the Free Software Foundation.

NAME="Google_Code_RSS_IRC_Bridge_Bot"
VERSION="0.1"

import simplejson

from twisted.internet import reactor, protocol, task
from twisted.web import server, resource
from twisted.words.protocols import irc

import re
import sys
import traceback
import urllib
import urllib2

ADMINS=['hatstand', 'davidsansome']
LMGTFY='http://lmgtfy.com/?q=%s'

class AnnounceBot(irc.IRCClient):
  username = "%s-%s" % (NAME, VERSION)
  sourceURL = "http://strobe.cc/"

  # I am a terrible person.
  instance = None

  # Intentionally 'None' until we join a channel
  channel = None

  # Prevent flooding
  lineRate = 3

  def __init__(self):
    self.hypnotoad = False

  def signedOn(self):
    self.join(self.factory.channel)
    AnnounceBot.instance = self

  def joined(self, channel):
    self.channel = self.factory.channel

  def left(self, channel):
    self.channel = None

  def trysay(self, msg):
    """Attempts to send the given message to the channel."""
    if self.channel:
      try:
        self.say(self.channel, msg)
        return True
      except Exception:
        print 'Failed to send message'
        traceback.print_exc()

  def privmsg(self, user, channel, message):
    print '%s from %s on %s' % (message, user, channel)
    if channel != '*':
      if '!' in user:
        user = user.split('!', 1)[0]

        # Only parse commands from private messages.
        if channel == self.nickname:
          self.ParseCommand(user, message)

  def SendMessage(self, message):
    if self.hypnotoad:
      message = message[:30] + 'ALL GLORY TO THE HYPNOTOAD!'
    self.trysay(message)

  def ParseCommand(self, user, message):
    if user not in ADMINS:
      self.msg(user, 'Forbidden')
      return

    if message == 'hypnotoad':
      self.hypnotoad = not self.hypnotoad
      self.msg(user, 'Hypnotoad: %s' % self.hypnotoad)
    elif message == 'test':
      self.SendMessage('Oh I\'m a lumberjack and I\'m ok. I sleep all night '
                       'and I work all day.')
    elif re.match(r'lmgtfy .*', message):
      query = re.sub(r'^lmgtfy *', '', message)
      self.LetMeGoogleThatForYou(query)

  def LetMeGoogleThatForYou(self, query):
    url = LMGTFY % urllib.quote(query)
    data = simplejson.dumps({'longUrl': url})
    print 'Shortening %s' % data
    request = urllib2.Request(
        'https://www.googleapis.com/urlshortener/v1/url?key='
        'AIzaSyAIctFM9t95xmDskXvJcz52AiU2X4TsX0Y',
        data,
        {'Content-Type': 'application/json'})
    response = urllib2.urlopen(request)
    response_data = response.read()
    print response_data
    url_json = simplejson.loads(response_data)
    if 'id' in url_json:
      self.SendMessage(url_json['id'])


class AnnounceBotFactory(protocol.ReconnectingClientFactory):
  protocol = AnnounceBot
  def __init__(self, channel):
    self.channel = channel

  def clientConnectionFailed(self, connector, reason):
    print "connection failed:", reason
    reactor.stop()

class WebHook(resource.Resource):
  isLeaf = True

  def render_GET(self, request):
    return 'foo'

  def render_POST(self, request):
    if request.path == '/commit':
      body = request.content
      if body:
        json = simplejson.load(body)

        for r in json['revisions']:
          short_url = r['short_url']
          message = r['message']
          if short_url:
            message = '(%s) %s' % (short_url, message)
          message = '\x033%s\x03\x02\x037 %s\x03\x02 %s' % (
              r['author'].encode("utf-8", "ignore"),
              r['revision'][:6].encode("utf-8", "ignore"),
              message.rstrip().replace('\n', ' ').encode("utf-8", "ignore"))
          AnnounceBot.instance.SendMessage(message)
    return 'ok'

if __name__ == '__main__':
  # All per-project customizations should be done here

  AnnounceBot.nickname = 'clementine-bot'
  fact = AnnounceBotFactory("#clementine")
  reactor.connectTCP('chat.freenode.net', 6667, fact)

  site = server.Site(WebHook())
  reactor.listenTCP(8080, site)

  reactor.run()
