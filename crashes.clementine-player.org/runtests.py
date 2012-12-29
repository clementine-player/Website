import os
import sys
import unittest


def main():
  if len(sys.argv) != 2:
    print "Usage: %s sdk_path" % sys.argv[0]
    return

  sdk_path = sys.argv[1]

  sys.path.insert(0, sdk_path)
  import dev_appserver
  dev_appserver.fix_sys_path()

  suite = unittest.TestLoader().discover(
      os.path.dirname(__file__), "*_test.py")
  unittest.TextTestRunner(verbosity=2).run(suite)


if __name__ == '__main__':
  main()
