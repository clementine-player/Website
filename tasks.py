from google.appengine.api.labs import taskqueue
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app


class Counter(db.Model):
  count = db.IntegerProperty(indexed=False, required=True)


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


application = webapp.WSGIApplication(
  [
    (r'/_tasks/counters', CounterWorker),
  ],
  debug=True)

def main():
  run_wsgi_app(application)

if __name__ == '__main__':
  main()
