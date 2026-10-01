# -*- coding: utf-8 -*-
"""Where Clementine Remote's store screenshots are: its release workflow
commits them to each release's tag (scripts/store_screenshots.py in
Android-Remote), numbered from 1.png."""

import re

REPO = 'clementine-player/Android-Remote'
SCREENSHOTS_PATH = 'fastlane/metadata/android/en-US/images/phoneScreenshots'
# Google Play shows at most eight.
MAX_SCREENSHOTS = 8

TAG = re.compile(r'v\d+(\.\d+)*$')
SCREENSHOT = re.compile(r'(\d+)\.png$')


def screenshot_url(tag, number):
  return 'https://raw.githubusercontent.com/%s/%s/%s/%d.png' % (
      REPO, tag, SCREENSHOTS_PATH, number)
