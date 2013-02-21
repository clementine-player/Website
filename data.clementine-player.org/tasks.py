from google.appengine.api import memcache
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


# This should try to serve from Zaphod as much as possible, as Cloudfront can
# get quite expensive.
class CheckRainyMood(webapp.RequestHandler):
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


app = webapp.WSGIApplication(
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
