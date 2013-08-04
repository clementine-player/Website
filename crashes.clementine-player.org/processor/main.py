import apiclient.discovery
import argparse
import base64
import cStringIO
import gflags
import gzip
import httplib2
import json
import logging
import oauth2client.client
import oauth2client.file
import oauth2client.tools
import os
import requests
import shutil
import subprocess
import tempfile
import time

import crash_pb2
import lrudiskcache

DEFAULT_CRASHREPORTING_HOSTNAME = "crashes.clementine-player.org"
DEFAULT_SYMBOLS_DIRECTORY = "symbols"
DEFAULT_STACKWALK_BINARY = "minidump_stackwalk"

SYMBOLS_URL = "http://storage.googleapis.com/clementine_crashes_symbols/%s/%s"
MINIDUMP_URL = "http://storage.googleapis.com/clementine_crashes_minidumps/%s"
PROCESS_CRASH_URL = "http://%s/api/upload/crashreport"

OAUTH2_CREDENTIALS_FILENAME = "~/.clementine-crash-processor.oauth2"
OAUTH2_AUTHORIZATION_SCOPES = [
    "https://www.googleapis.com/auth/taskqueue",
    "https://www.googleapis.com/auth/devstorage.read_only",
]
OAUTH2_CLIENT_ID = "710082478004.apps.googleusercontent.com"
OAUTH2_CLIENT_SECRET = "nrpCC58ECHs7YXY4z-m5pFRl"

PROJECT_NAME = "s~clementine-crashes-hrd"
TASKQUEUE_NAME = "raw-crashes"
NUM_TASKS = 100
LEASE_SECS = 30 * NUM_TASKS
POLL_INTERVAL_SECS = 30 * 60 # 30 minutes


class FetchSymbolsError(Exception):
  pass


class SymbolCache(object):
  def __init__(self, directory, http):
    self.directory = directory
    self.http = http
    self.disk_cache = lrudiskcache.LRUDiskCache(directory)

  def CacheKey(self, binary_name, binary_hash):
    return os.path.join(binary_name, binary_hash, "%s.sym" % binary_name)

  def LoadSymbols(self, binary_name, binary_hash):
    key = self.CacheKey(binary_name, binary_hash)
    if self.disk_cache.ContainsMissing(key) or self.disk_cache.Contains(key):
      return

    # Get the symbols from the server.
    url = SYMBOLS_URL % (binary_name, binary_hash)
    response, content = self.http.request(url)

    if response.status == 404:
      # These symbols are probably never going to exist, so don't request them
      # again.
      logging.info("Missing symbols for %s (%s)", binary_name, binary_hash)
      self.disk_cache.SetMissing(key)
      return

    if response.status != 200:
      raise FetchSymbolsError(response.status, content)

    logging.info("Downloaded symbols for %s (%s)", binary_name, binary_hash)

    # Decompress the data and write it to the cache.
    buf = cStringIO.StringIO(content)
    gzip_file = gzip.GzipFile(fileobj=buf)
    self.disk_cache.WriteFile(key, gzip_file.read())


class Processor(object):
  def __init__(self, symbol_cache, stackwalk_binary):
    self.symbol_cache = symbol_cache
    self.stackwalk_binary = stackwalk_binary

  def ParseStackwalkOutput(self, stdout):
    ret = crash_pb2.Crash()

    processing_stackframes = False
    for line in stdout.splitlines():
      parts = line.split("|")
      if not processing_stackframes:
        if len(parts) == 1 and not parts[0]:
          processing_stackframes = True
        elif parts[0] == "OS":
          ret.metadata.os = parts[1]
          ret.metadata.os_version = parts[2]
        elif parts[0] == "CPU":
          ret.metadata.cpu = parts[1]
          ret.metadata.cpu_info = parts[2]
          ret.metadata.cpu_count = int(parts[3])
        elif parts[0] == "Crash":
          ret.metadata.crash_reason = parts[1]
          ret.metadata.crash_address = parts[2]
          ret.metadata.crash_thread = int(parts[3])
        elif parts[0] == "Module":
          module = ret.module.add()
          module.code_file = parts[1]
          module.version = parts[2]
          module.debug_file = parts[3]
          module.debug_hash = parts[4]
          module.start_address = parts[5]
          module.end_address = parts[6]
          module.is_main_module = bool(int(parts[7]))

      else:
        thread_no = int(parts[0])
        frame_no = int(parts[1])

        if thread_no >= len(ret.thread):
          thread = ret.thread.add()
        else:
          thread = ret.thread[thread_no]

        if frame_no >= len(thread.frame):
          frame = thread.frame.add()
        else:
          frame = thread.frame[frame_no]

        frame.module = parts[2]
        frame.function = self.CPPDemangle(parts[3])
        frame.filename = parts[4]
        frame.offset = parts[6]

        if parts[5]:
          frame.line = int(parts[5])

    return ret

  def CPPDemangle(self, symbol):
    handle = subprocess.Popen(
        ["c++filt", "-n", symbol], stdout=subprocess.PIPE)
    output = handle.communicate()[0]

    if handle.returncode == 0:
      return output.strip()

    logging.warning("Failed to demangle C++ symbol '%s'", symbol)
    return symbol

  def ProcessDump(self, filename):
    # Run stalkwalk to get a list of modules we need to load symbols for.
    output = subprocess.check_output(
        [self.stackwalk_binary, "-m", filename], stderr=subprocess.PIPE)

    crash_pb = self.ParseStackwalkOutput(output)
    for module in crash_pb.module:
      if module.debug_hash == "000000000000000000000000000000000":
        continue
      self.symbol_cache.LoadSymbols(module.debug_file, module.debug_hash)

    # Run stackwalk again with these symbols to get proper stacks.
    output = subprocess.check_output(
        [self.stackwalk_binary, "-m", filename, self.symbol_cache.directory],
        stderr=subprocess.PIPE)

    crash_pb = self.ParseStackwalkOutput(output)
    return crash_pb


def ProcessTask(task_id, crash_key, http, crashreporting_hostname, processor):
  # Fetch the crash report
  url = MINIDUMP_URL % crash_key
  response, content = http.request(url)

  if response.status != 200:
    logging.warning("Request for '%s' failed with status %d.  Content: %s",
        url, response.status, content)
    return

  with tempfile.NamedTemporaryFile() as temp_file:
    # Write it to a temporary file.
    temp_file.write(content)
    temp_file.flush()

    # Analyze it.
    crash_pb = processor.ProcessDump(temp_file.name)

  # Serialise the crash and send it back to appengine.
  url = PROCESS_CRASH_URL % crashreporting_hostname
  response = requests.post(url, data={
      "crash_key": crash_key,
      "crash_pb_b64": base64.b64encode(crash_pb.SerializeToString()),
      "task_id": task_id,
  })
  if not response.ok:
    logging.warning("Failed to post updated crash proto to '%s' "
                    "- status %d.  Content: %s",
        url, response.status_code, response.text)


def PollQueue(task_api, http, crashreporting_hostname, processor):
  while True:
    start_time = time.time()

    # Get some pending tasks.
    try:
      response = task_api.tasks().lease(project=PROJECT_NAME,
                                        taskqueue=TASKQUEUE_NAME,
                                        leaseSecs=LEASE_SECS,
                                        numTasks=NUM_TASKS).execute()
    except Exception:
      logging.exception("Error leasing tasks")

    # Process the tasks.
    for task in response.get("items", []):
      try:
        payload = json.loads(base64.b64decode(task["payloadBase64"]))
        logging.info("Processing task: %s", payload)

        ProcessTask(
            task["id"], payload["key"], http, crashreporting_hostname,
            processor)
      except Exception:
        logging.exception("Error processing task")

    # Wait a little while before polling again.
    wait_time = (start_time + POLL_INTERVAL_SECS) - time.time()
    if wait_time > 0:
      logging.info("Sleeping for %d seconds", wait_time)
      time.sleep(wait_time)


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--symbols_directory", default=DEFAULT_SYMBOLS_DIRECTORY)
  parser.add_argument("--stackwalk_binary", default=DEFAULT_STACKWALK_BINARY)
  parser.add_argument("--crashreporting_hostname", default=DEFAULT_CRASHREPORTING_HOSTNAME)
  parser.add_argument("--onlyone", metavar="key",
      help="Process a single crash, don't poll the task queue")
  args = parser.parse_args()

  gflags.FLAGS.SetDefault("auth_local_webserver", False)

  logging.basicConfig(level=logging.DEBUG,
                      format="%(asctime)s %(levelname)-7s %(message)s")
  logging.getLogger("requests").setLevel(logging.WARNING)

  # Do the oauth stuff.
  oauth_cred_filename = os.path.expanduser(OAUTH2_CREDENTIALS_FILENAME)
  logging.info("Using oauth2 credentials store in '%s'", oauth_cred_filename)

  storage = oauth2client.file.Storage(oauth_cred_filename)
  credentials = storage.get()
  if credentials is None or credentials.invalid:
    flow = oauth2client.client.OAuth2WebServerFlow(
        OAUTH2_CLIENT_ID, OAUTH2_CLIENT_SECRET,
        OAUTH2_AUTHORIZATION_SCOPES)
    credentials = oauth2client.tools.run(flow, storage)

  # Create an HTTP client and API client.
  http = credentials.authorize(httplib2.Http())
  task_api = apiclient.discovery.build("taskqueue", "v1beta2", http=http)

  # Create the symbols directory if it doesn't exist already.
  try:
    os.makedirs(args.symbols_directory)
  except os.error:
    pass

  # Load cached symbols.
  cache = SymbolCache(args.symbols_directory, http)
  processor = Processor(cache, args.stackwalk_binary)

  if args.onlyone:
    # Just process this one crash.
    ProcessTask(
        "<unknown>", args.onlyone, http, args.crashreporting_hostname,
        processor)
  else:
    # Start polling for new tasks.
    PollQueue(task_api, http, args.crashreporting_hostname, processor)


if __name__ == "__main__":
  main()
