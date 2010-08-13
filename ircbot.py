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
import urllib2

class AnnounceBot(irc.IRCClient):

    username = "%s-%s" % (NAME, VERSION)
    sourceURL = "http://strobe.cc/"

    # I am a terrible person.
    instance = None

    # Intentionally 'None' until we join a channel
    channel = None

    # Prevent flooding
    lineRate = 3

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
            except: pass

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
            message = 'r%d: %s' % (r['revision'], r['message'].rstrip())
            AnnounceBot.instance.trysay(message)
      return 'ok'

def strip_tags(value):
    return re.sub(r'<[^>]*?>', '', value)

def announce(feed):
    new = feed.update()
    for entry in new:
        msg = '%s: %s' % (strip_tags(entry['title']), entry['link'])
        if AnnounceBot.instance:
            AnnounceBot.instance.trysay(msg.replace('\n', '').encode('utf-8'))

if __name__ == '__main__':
    # All per-project customizations should be done here

    AnnounceBot.nickname = 'clementine-bot'
    fact = AnnounceBotFactory("#clementine")
    reactor.connectTCP('chat.freenode.net', 6667, fact)

    site = server.Site(WebHook())
    reactor.listenTCP(8080, site)

    reactor.run()

