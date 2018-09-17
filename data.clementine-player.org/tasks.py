from google.appengine.api import app_identity
from google.appengine.api import memcache
from google.appengine.api import urlfetch
from google.appengine.api import xmpp
from google.appengine.api.labs import taskqueue
from google.appengine.ext import db

import difflib
import json
import logging
import webapp2

import clementine
import models

LIST_FILES = 'https://api.github.com/repos/%(owner)s/%(repo)s/pulls/%(number)s/files'
POST_COMMENT = (
    'https://api.github.com/repos/%(owner)s/%(repo)s/issues/%(number)s/comments')
CREATE_GIST = 'https://api.github.com/gists'

TOKEN_PURPOSE='github-format'


class Error(Exception):
  pass


class GithubApiError(Error):
  pass


class Counter(db.Model):
  count = db.IntegerProperty(indexed=False, required=True)


class CounterSnapshot(db.Model):
  counter = db.ReferenceProperty(Counter, required=True, collection_name='snapshots')
  count = db.IntegerProperty(indexed=False, required=True)
  date = db.DateProperty(auto_now_add=True)


class CounterWorker(webapp2.RequestHandler):
  def post(self):
    key = self.request.get('key')
    def transaction():
      counter = Counter.get_by_key_name(key)
      if counter is None:
        counter = Counter(key_name=key, count=1)
      else:
        counter.count += 1
      counter.put()

    db.run_in_transaction(transaction)


class SnapshotTask(webapp2.RequestHandler):
  def get(self):
    taskqueue.add(url='/_tasks/snapshot')
    self.response.out.write('OK')

  def post(self):
    counters = Counter.all().fetch(10)
    puts = []
    for counter in counters:
      snapshot = CounterSnapshot(counter=counter, count=counter.count)
      puts.append(snapshot)

    db.put(puts)


# This should try to serve from Zaphod as much as possible, as Cloudfront can
# get quite expensive.
class CheckRainyMood(webapp2.RequestHandler):
  def get(self):
    # Check Zaphod is serving
    try:
      response = urlfetch.fetch(
          clementine.RAINYMOOD_URL, method=urlfetch.HEAD, deadline=10)
      if response.status_code < 200 or response.status_code > 300:
        self.SwitchToBackup()
      else:
        memcache.set(
            clementine.RAINYMOOD_MEMCACHE_KEY, clementine.RAINYMOOD_URL)
    except urlfetch.Error, e:
      self.SwitchToBackup()

  def SwitchToBackup(self):
    # Zaphod is down; switch to Cloudfront.
    logging.error('Switching to backup rainymood url')
    memcache.set(
        clementine.RAINYMOOD_MEMCACHE_KEY, clementine.BACKUP_RAINYMOOD_URL)


class FormatPullRequest(webapp2.RequestHandler):
  def __init__(self, request, response):
    webapp2.RequestHandler.__init__(self, request, response)
    self.output = ''

  def post(self):
    # We will need the oauth token for posting a gist later so start the
    # query now.
    token_future = models.OAuthToken.query(
        models.OAuthToken.purpose == TOKEN_PURPOSE).get_async()

    owner = self.request.get('owner')
    repo = self.request.get('repo')
    number = self.request.get('number')
    list_files_response = urlfetch.fetch(
        LIST_FILES % {
          'owner': self.request.get('owner'),
          'repo': self.request.get('repo'),
          'number': self.request.get('number')
        })
    if list_files_response.status_code != 200:
      raise GithubApiError('Failed to list files in pull request')

    content = json.loads(list_files_response.content)
    files = [(x['filename'], x['raw_url']) for x in content]

    rpcs = []
    for f in files:
      rpc = urlfetch.create_rpc()
      urlfetch.make_fetch_call(rpc, f[1])
      rpcs.append((rpc, f[0]))

    for rpc in rpcs:
      rpc[0].wait()

    # All file content RPCs finished.
    # TODO: Start the formatting RPCs as soon as individual content RPCs return.
    file_contents = [(rpc[1], rpc[0].get_result().content) for rpc in rpcs]
    rpcs = []

    for content in file_contents:
      rpc = urlfetch.create_rpc()
      rpc.callback = self.CreateCallback(rpc, content)
      urlfetch.make_fetch_call(
          rpc,
          'http://clang.clementine-player.org/format',
          method=urlfetch.POST,
          payload=content[1])
      rpcs.append(rpc)

    for rpc in rpcs:
      rpc.wait()

    # Now we need the oauth token.
    token_result = token_future.get_result()
    if token_result is None:
      raise GithubApiError('No oauth token available')
    else:
      self.oauth_token = token_result.token

    # Post the diff as a gist
    gist_url = self.CreateGist(
        'Patch for %s/%s issue %s' % (owner, repo, number),
        self.output)
    self.PostComment(
        owner, repo, number,
        'Successfully ran clang format on pull request:\n%s' % gist_url)


  def CreateCallback(self, rpc, original_content):
    return lambda: self.HandleResult(rpc, original_content)

  def HandleResult(self, rpc, original_content):
      filename = original_content[0]
      orig = original_content[1]
      new = rpc.get_result().content
      diff = difflib.unified_diff(
          orig.split('\n'),
          new.split('\n'),
          'a/%s' % filename,
          'b/%s' % filename,
          lineterm='')
      unified_diff = '\n'.join(diff)
      self.output += unified_diff
      self.output += '\n\n'

  def PostComment(self, owner, repo, number, body):
    url = POST_COMMENT % {
      'owner': 'hatstand',
      'repo': 'ilovelamp',
      'number': 1
    }
    result = urlfetch.fetch(
        url=url,
        method=urlfetch.POST,
        headers={
          'Authorization': 'token %s' % self.oauth_token,
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        payload=json.dumps({
          'body': body,
        }))
    if result.status_code >= 400:
      logging.debug('Posting comment: %d %s', result.status_code, result.content)
      raise GithubApiError('Failed to post comment')

  def CreateGist(self, title, body):
    result = urlfetch.fetch(
        url=CREATE_GIST,
        method=urlfetch.POST,
        headers={
          'Authorization': 'token %s' % self.oauth_token,
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        payload=json.dumps({
          'description': title,
          'public': True,
          'files': {
            'clang.patch': {
              'content': body,
            }
          }
        }))
    if result.status_code > 200 and result.status_code < 400:
      return json.loads(result.content)['html_url']
    else:
      logging.debug('Posting gist: %d %s', result.status_code, result.content)
      raise GithubApiError('Creating gist failed')


class TransifexPullPage(webapp2.RequestHandler):
  def get(self):
    token, _ = app_identity.get_access_token('https://www.googleapis.com/auth/cloud-platform')
    response = urlfetch.fetch(
        'https://cloudbuild.googleapis.com/v1/projects/clementine-data/triggers/08f31055-68ed-4a66-a3f4-5edace8a1836:run',
        method=urlfetch.POST,
        payload=json.dumps({
            'projectId': 'clementine-data',
            'repoName': 'github-clementine-player-clementine',
            'branchName': 'master',
        }),
        headers={
          'Authorization': 'Bearer {}'.format(token),
          'Content-Type': 'application/json',
        })
    if response.status_code != 200:
      raise Exception('Triggering build failed: {}'.format(response.content))
    result = json.loads(response.content)
    self.response.headers['Content-Type'] = 'application/json'
    self.response.write(json.dumps(result, indent=2))


app = webapp2.WSGIApplication(
  [
    (r'/_tasks/counters', CounterWorker),
    (r'/_tasks/snapshot', SnapshotTask),
    (r'/_tasks/rainymood', CheckRainyMood),
    (r'/_tasks/formatpullrequest', FormatPullRequest),
    (r'/_tasks/transifex-pull', TransifexPullPage),
  ],
  debug=True)
