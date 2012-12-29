import unittest

import upload


class UploadTest(unittest.TestCase):
  def setUp(self):
    self.handler = upload.UploadHandlerPage()

  def testShortenOSVersion(self):
    data = [
      ("Windows 7", "Windows 7"),
      ('DISTRIB_ID=LinuxMint DISTRIB_RELEASE=12 DISTRIB_CODENAME=lisa DISTRIB_DESCRIPTION="Linux Mint 12 Lisa"',
        'Linux Mint 12 Lisa'),
      ('DISTRIB_ID=Ubuntu DISTRIB_RELEASE=10.04 DISTRIB_CODENAME=lucid DISTRIB_DESCRIPTION="Ubuntu 10.04.4 LTS"',
        'Ubuntu 10.04.4 LTS'),
      ('DISTRIB_ID=Something DISTRIB_RELEASE=1234', 'Something 1234'),
      ('DISTRIB_ID=Something', 'Something'),
    ]

    for os_version, expected in data:
      self.assertEqual(expected, self.handler.ShortenOSVersion(os_version))
