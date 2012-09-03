import feedparser
import re
import urllib2
import urlparse

FEED='http://code.google.com/feeds/p/clementine-player/gitchanges/basic'

def FetchCommitLogSince(revision, feed):
  response = urllib2.urlopen(feed)
  xml = response.read()
  feed = feedparser.parse(xml)

  entries = feed['entries']
  messages = []
  expression = re.compile(r'<br />\n <br />(.*)', re.DOTALL)
  for e in entries:
    url = e['links'][0]['href']
    parsed_url = urlparse.urlparse(url)
    parsed_query = urlparse.parse_qs(parsed_url.query)
    rev = parsed_query['r'][0]
    if rev == revision:
      break

    result = expression.search(e['content'][0]['value'])
    if result:
      messages.append(result.group(1))
  return messages


if __name__ == '__main__':
  print FetchCommitLogSince(u'1c338455c3c84cb86df6c1ac2223a4cb1bee3f0b', FEED)
