import unittest

import crashes

class CrashesTest(unittest.TestCase):
  def testLinkify(self):
    self.assertEquals(
        "http://code.google.com/p/clementine-player/source/browse/%s?r=123abcd#%d",
        crashes.CodesiteURLTemplate("1.1.1-123-g123abcd"))

    self.assertEquals(
        "http://code.google.com/p/clementine-player/source/browse/%s?name=1.1.1#%d",
        crashes.CodesiteURLTemplate("1.1.1"))

    self.assertEquals(
        "http://code.google.com/p/clementine-player/source/browse/%s?name=1.1#%d",
        crashes.CodesiteURLTemplate("1.1"))

    self.assertEquals(
        "http://code.google.com/p/clementine-player/source/browse/%s#%d",
        crashes.CodesiteURLTemplate("wat"))
