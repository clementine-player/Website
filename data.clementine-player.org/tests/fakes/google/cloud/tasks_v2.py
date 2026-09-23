"""Minimal fake of google.cloud.tasks_v2 for local smoke testing.

Records enqueued tasks instead of actually delivering them -- there's
nothing to "deliver" to locally, so the test just asserts on what would
have been sent.
"""

TASKS = []


class HttpMethod(object):
  POST = 'POST'
  GET = 'GET'


class CloudTasksClient(object):
  def queue_path(self, project, location, queue):
    return 'projects/%s/locations/%s/queues/%s' % (project, location, queue)

  def create_task(self, parent, task):
    entry = {'parent': parent, 'task': task}
    TASKS.append(entry)
    return task
