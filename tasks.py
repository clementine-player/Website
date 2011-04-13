from google.appengine.api import urlfetch
from google.appengine.api import xmpp
from google.appengine.api.labs import taskqueue
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app

import logging

import clementine


class Counter(db.Model):
  count = db.IntegerProperty(indexed=False, required=True)


class CounterSnapshot(db.Model):
  counter = db.ReferenceProperty(Counter, required=True, collection_name='snapshots')
  count = db.IntegerProperty(indexed=False, required=True)
  date = db.DateProperty(auto_now_add=True)


class CounterWorker(webapp.RequestHandler):
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


class SnapshotTask(webapp.RequestHandler):
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


class CheckRainyMood(webapp.RequestHandler):
  def get(self):
    url = clementine.CURRENT_RAINYMOOD_URL
    try:
      response = urlfetch.fetch(url, method=urlfetch.HEAD, deadline=10)
      if response.status_code < 200 or response.status_code > 300:
        self.Notify('Check failed with code: %d' % response.status_code)
    except urlfetch.Error, e:
      self.Notify('Check failed with error: %s' % e)

  def Notify(self, reason):
    try:
      xmpp.send_message('john.maguire@gmail.com', 'Rainy Mood:\n%s' % reason)
    except:
      logging.error('Failed to send rainy mood check: %s', reason)


application = webapp.WSGIApplication(
  [
    (r'/_tasks/counters', CounterWorker),
    (r'/_tasks/snapshot', SnapshotTask),
    (r'/_tasks/rainymood', CheckRainyMood),
  ],
  debug=True)

def main():
  run_wsgi_app(application)

if __name__ == '__main__':
  main()
