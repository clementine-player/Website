import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'settings'
from google.appengine.dist import use_library
use_library('django', '1.1')

from google.appengine.api import urlfetch
from google.appengine.api import users
from google.appengine.api import xmpp
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app

from django.utils import simplejson

import hmac
import logging
import re
import urllib2

import models

class ProjectsPage(webapp.RequestHandler):
  TEMPLATE='projects.html'
  def get(self):
    projects = models.GoogleCode.all().fetch(10)

    path = os.path.join(os.path.dirname(__file__), self.TEMPLATE)
    user = users.get_current_user()

    query = models.Follower.gql('WHERE user = :user', user=user)
    following = [f.project for f in query]
    following_names = [p.name for p in following]

    self.response.out.write(template.render(path,
        { 'tab': 'follow',
          'user': user,
          'sign_in_url': users.create_login_url('/projects'),
          'sign_out_url': users.create_logout_url('/projects'),
          'projects': [p for p in projects if p.name not in following_names],
          'following': following}))


class AddProjectPage(webapp.RequestHandler):
  def post(self):
    if not users.is_current_user_admin():
      self.error(403)
      return

    name = self.request.get('name')
    secret = self.request.get('secret')

    project = models.GoogleCode(name=name, secret=secret)
    project.put()
    self.response.out.write('ok')


class FollowPage(webapp.RequestHandler):
  def post(self):
    user = users.get_current_user()
    project_name = self.request.get('project')

    project = models.GoogleCode.gql('WHERE name = :name', name=project_name).get()
    if project is None:
      self.error(404)
      self.response.out.write('Project not found')
      return

    follower = models.Follower.gql('WHERE user = :user AND project = :project',
                                   user=user, project=project).get()
    if follower is not None:
      self.error(304)
      self.response.out.write('Already exists')
      return

    new_follower = models.Follower(user=user, project=project)
    new_follower.put()

    xmpp.send_invite(user.email())


class UnfollowPage(webapp.RequestHandler):
  def post(self):
    user = users.get_current_user()
    project_name = self.request.get('project')
    project = models.GoogleCode.gql('WHERE name = :name', name=project_name).get()
    follower = models.Follower.gql('WHERE user = :user AND project = :project',
                                   user=user, project=project).get()
    if follower is None:
      self.error(404)
      return

    follower.delete()
    self.response.out.write('OK')


class GitCommitPage(webapp.RequestHandler):
  def post(self):
    json = simplejson.loads(self.request.get('payload'))
    commits = json['commits']
    project_name = json['repository']['name']

    for commit in commits:
      message = '%(project_name)s:%(user)s %(change)s %(url)s' % {
          'project_name': project_name,
          'user': commit['author']['name'],
          'change': commit['message'],
          'url': commit['url'],
      }
      logging.info('Git commit: %s', message)
      for user in ['john.maguire@gmail.com', 'davidsansome@gmail.com']:
        try:
          if xmpp.get_presence(user):
            status_code = xmpp.send_message(user, message)
            if status_code != xmpp.NO_ERROR:
              logging.error('Failed to send XMPP message to %s', user)
        except xmpp.Error, e:
          logging.warn('User %s offline: %s', user, e)


class CommitPage(webapp.RequestHandler):
  IRC_WEBHOOK='http://zaphod.purplehatstands.com:8080/commit'

  def Shorten(self, url):
    data = simplejson.dumps({'longUrl':url})
    request = urllib2.Request(
        'https://www.googleapis.com/urlshortener/v1/url?key='
        'AIzaSyB0MCh4zww04T6wj9z-imRHtHAGWT58TWo',
        data,
        {'Content-Type': 'application/json'})
    url_json = simplejson.load(urllib2.urlopen(request))
    if 'id' in url_json:
      return url_json['id']

  def post(self):
    json = simplejson.loads(self.request.body)
    logging.debug('Received JSON: %s', json)
    project_name = json['project_name']
    project = models.GoogleCode.gql('WHERE name = :name', name=project_name).get()
    if project is None:
      self.error(404)
      return

    auth = self.request.headers['Google-Code-Project-Hosting-Hook-Hmac']
    m = hmac.new(project.secret)
    m.update(self.request.body)
    if auth != m.hexdigest():
      self.error(403)
      return

    repo_path = json['repository_path']
    repo = None
    regex = '%s\.([^/]+)' % project_name
    match = re.search(regex, repo_path)
    if match is not None:
      repo = match.group(1)

    # Fill in all the short URLs.
    for r in json['revisions']:
      url = 'http://code.google.com/p/%s/source/detail?r=%s' % (project_name, r['revision'])
      if repo is not None:
        url += '&repo=%s' % repo

      try:
        short_url = self.Shorten(url)
        r['short_url'] = short_url
      except urllib2.URLError, ValueError:
        # Weird but we can error here and Google Code will try again later.
        self.error(500)
        logging.error('Failed to construct short url from %s', url)
        return

    # Notify IRC bot on Zaphod.
    rpc = urlfetch.create_rpc()
    urlfetch.make_fetch_call(rpc, self.IRC_WEBHOOK, payload=self.request.body, method=urlfetch.POST)

    users = [x.user.email() for x in project.followers.fetch(100)]
    messages = []
    for r in json['revisions']:
      messages.append('%s\nr%s: %s - %s' % (project_name, r['revision'][:6], r['message'], r['short_url']))

    logging.info('Sending messages: %s', messages)
    logging.info('to users: %s', users)

    for user in users:
      try:
        if xmpp.get_presence(user):
          for message in messages:
            status_code = xmpp.send_message(user, message)
            if status_code != xmpp.NO_ERROR:
              logging.error('Failed to send XMPP message to %s', user)
      except xmpp.Error:
        pass

    try:
      result = rpc.get_result()
      if result.status_code != 200:
        logging.warning('IRC webhook failed: %d', result.status_code)
    except urlfetch.Error, e:
      logging.warning('IRC webhook failed: %s', e)



application = webapp.WSGIApplication(
  [
    (r'/', ProjectsPage),
    (r'/projects', ProjectsPage),
    (r'/projects/add', AddProjectPage),
    (r'/projects/follow', FollowPage),
    (r'/projects/unfollow', UnfollowPage),
    (r'/projects/commit', CommitPage),
    (r'/projects/gitcommit', GitCommitPage),
  ],
  debug=True)

def main():
  run_wsgi_app(application)

if __name__ == '__main__':
  main()
