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
import urllib
import urllib2

ADMINS=['hatstand', 'davidsansome']

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
      except:
        print 'Failed to send message'

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



class AnnounceBotFactory(protocol.ReconnectingClientFactory):
  protocol = AnnounceBot
  def __init__(self, channel):
    self.channel = channel

  def clientConnectionFailed(self, connector, reason):
    print "connection failed:", reason
    reactor.stop()

class WebHook(resource.Resource):
  isLeaf = True

  def Shorten(self, url):
    try:
      data = simplejson.dumps({'longUrl':url})
      request = urllib2.Request(
          'https://www.googleapis.com/urlshortener/v1/url?key='
          'AIzaSyB0MCh4zww04T6wj9z-imRHtHAGWT58TWo',
          data,
          {'Content-Type': 'application/json'})
      url_json = simplejson.load(urllib2.urlopen(request))
      if 'id' in url_json:
        return url_json['id']
    except urllib2.URLError, ValueError:
      pass

  def render_GET(self, request):
    return 'foo'

  def render_POST(self, request):
    if request.path == '/commit':
      body = request.content
      if body:
        json = simplejson.load(body)
        project_name = json['project_name']
        repo_path = json['repository_path']
        regex = '%s\.([^/]+)' % project_name
        match = re.search(regex, repo_path)
        repo = None
        if match is not None:
          repo = match.groups(1)

        for r in json['revisions']:
          url = ('http://code.google.com/p/clementine-player/source/detail?r=%s' %
              r['revision'])
          if repo is not None:
            url += '&repo=%s' % repo
          short_url = self.Shorten(url)
          message = r['message']
          if short_url:
            message = '(%s) %s' % (short_url, message)
          message = '\x033%s\x03\x02\x037 %s\x03\x02 %s' % (
              r['author'], r['revision'][:6], message.rstrip().replace('\n', ' '))
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
