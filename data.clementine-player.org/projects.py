from google.appengine.api import urlfetch
from google.appengine.ext import db

import hmac
import json
import logging
import re
import urllib2
import webapp2

import ipaddr
import models


IRC_WEBHOOK = 'http://zaphod.purplehatstands.com:8080/commit'
GITHUB_NETWORK = ipaddr.IPv4Network('192.30.252.0/22')


def Shorten(url):
  data = json.dumps({'longUrl':url})
  request = urllib2.Request(
      'https://www.googleapis.com/urlshortener/v1/url?key='
      'AIzaSyAIctFM9t95xmDskXvJcz52AiU2X4TsX0Y',
      data,
      {'Content-Type': 'application/json'})
  url_json = json.load(urllib2.urlopen(request))
  if 'id' in url_json:
    return url_json['id']


def HasSeenRevisionBefore(project_name, revision):
  # Check if we've ever seen this revision before.
  query = models.KnownRevision.all(keys_only=True)
  query.filter("project_name =", project_name)
  query.filter("sha1 =", revision)

  if query.get() is not None:
    # We've seen this one before - ignore it.
    logging.debug("Ignoring known revision: %s" % revision)
    return True

  # Record this revision so we never notify about it again.
  entity = models.KnownRevision()
  entity.project_name = project_name
  entity.sha1 = revision
  entity.put()
  return False


def TellIrcBot(data):
  rpc = urlfetch.create_rpc()
  urlfetch.make_fetch_call(
      rpc, IRC_WEBHOOK, payload=json.dumps(data), method=urlfetch.POST)

  try:
    result = rpc.get_result()
    if result.status_code != 200:
      logging.warning('IRC webhook failed: %d', result.status_code)
  except urlfetch.Error as e:
    logging.warning('IRC webhook failed: %s', e)


class GithubCommitPage(webapp2.RequestHandler):
  def post(self):
    peer = ipaddr.IPv4Address(self.request.remote_addr)
    if peer not in GITHUB_NETWORK:
      self.error(403)
      return

    json_data = json.loads(self.request.get('payload'))
    project_name = json_data['repository']['name']

    revisions = []

    for commit in json_data['commits']:
      if HasSeenRevisionBefore(project_name, commit['id']):
        continue

      try:
        short_url = Shorten(commit['url'])
      except urllib2.URLError, ValueError:
        short_url = commit['url']

      revisions.append({
          'short_url': short_url,
          'author': '%s <%s>' % (
              commit['author']['name'], commit['author']['email']),
          'revision': commit['id'],
          'message': commit['message'],
      })

    TellIrcBot({'revisions': revisions})


class CommitPage(webapp2.RequestHandler):
  def post(self):
    json_data = json.loads(self.request.body)
    logging.debug('Received JSON: %s', json_data)
    project_name = json_data['project_name']
    project = models.GoogleCode.gql('WHERE name = :name', name=project_name).get()
    if project is None:
      self.error(404)
      return

    auth = self.request.headers['Google-Code-Project-Hosting-Hook-Hmac']
    m = hmac.new(str(project.secret))
    m.update(self.request.body)
    if auth != m.hexdigest():
      self.error(403)
      return

    repo_path = json_data['repository_path']
    repo = None
    regex = '%s\.([^/]+)' % project_name
    match = re.search(regex, repo_path)
    if match is not None:
      repo = match.group(1)

    new_revisions = []
    for r in json_data["revisions"]:
      if HasSeenRevisionBefore(project_name, r["revision"]):
        continue

      # It's a new revision so fill in the short URL
      url = 'http://code.google.com/p/%s/source/detail?r=%s' % (project_name, r['revision'])
      if repo is not None:
        url += '&repo=%s' % repo

      try:
        short_url = Shorten(url)
        r['short_url'] = short_url
      except urllib2.URLError, ValueError:
        # Weird but we can error here and Google Code will try again later.
        self.error(500)
        logging.error('Failed to construct short url from %s', url)
        return

      new_revisions.append(r)

    if not new_revisions:
      logging.debug("All revisions had been seen before, exiting")
      return

    json_data["revisions"] = new_revisions

    TellIrcBot(json_data)


class RedirectPage(webapp2.RequestHandler):
  def get(self):
    self.redirect('http://www.clementine-player.org/')


app = webapp2.WSGIApplication(
  [
    (r'/', RedirectPage),
    (r'/projects/commit', CommitPage),
    (r'/projects/commit/github', GithubCommitPage),
  ],
  debug=True)
