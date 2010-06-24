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


class CommitPage(webapp.RequestHandler):
  def post(self):
    json = simplejson.loads(self.request.body)
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

    users = [x.user.email() for x in project.followers.fetch(100)]
    for user in users:
      if xmpp.get_presence(user):
        for r in json['revisions']:
          link = 'http://code.google.com/p/%s/source/detail?r=%d' % (project_name, r['revision'])
          message = '%s\nr%d: %s - %s' % (project_name, r['revision'], r['message'], link)
          status_code = xmpp.send_message(user, message)
          if status_code != xmpp.NO_ERROR:
            logging.error('Failed to send XMPP message to %s', user)


application = webapp.WSGIApplication(
  [
    (r'/', ProjectsPage),
    (r'/projects', ProjectsPage),
    (r'/projects/add', AddProjectPage),
    (r'/projects/follow', FollowPage),
    (r'/projects/unfollow', UnfollowPage),
    (r'/projects/commit', CommitPage),
  ],
  debug=True)

def main():
  run_wsgi_app(application)

if __name__ == '__main__':
  main()
