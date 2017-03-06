#!/usr/bin/python

import base64
import json
import logging
import os
import requests
import urllib2

SPOTIFY_AUTH_URL = 'https://accounts.spotify.com/api/token'
SPOTIFY_SEARCH_URL = 'https://api.spotify.com/v1/search'
SPOTIFY_ARTIST_URL = 'https://api.spotify.com/v1/artists/%s'
TIMEOUT = 10


def CreateAuthorizationHeader():
  return 'Basic %s' % base64.b64encode('%s:%s' % (
      os.environ['SPOTIFY_CLIENT_ID'], os.environ['SPOTIFY_CLIENT_SECRET']))


def CreateBearerHeader(token):
  return 'Bearer %s' % token


def ExtractSpotifyId(full_id):
  return full_id.split(':')[2]


def lambda_handler(event, context):
  try:
    auth_response = requests.post(
        SPOTIFY_AUTH_URL, {
            'grant_type': 'client_credentials',
        },
        headers={'Authorization': CreateAuthorizationHeader()},
        timeout=TIMEOUT)
    auth_response.raise_for_status()
    auth_token = auth_response.json()['access_token']

    search_response = requests.get(
        SPOTIFY_SEARCH_URL, {
            'q': event['artist'],
            'limit': '1',
            'type': 'artist',
        },
        headers={'Authorization': CreateBearerHeader(auth_token)},
        timeout=TIMEOUT)
    search_response.raise_for_status()
    if len(search_response.json()['artists']['items']) < 1:
      return '{}'

    artist_id = ExtractSpotifyId(
        search_response.json()['artists']['items'][0]['uri'])

    artist_response = requests.get(
        SPOTIFY_ARTIST_URL % artist_id,
        headers={'Authorization': CreateBearerHeader(auth_token)},
        timeout=TIMEOUT)
    artist_response.raise_for_status()

    return json.dumps(artist_response.json()['images'])
  except urllib2.HTTPError as e:
    logging.error('Request failed: %s', e)
    return '{}'
  except requests.exceptions.RequestException as e:
    logging.error('Request failed: %s', e)
    return '{}'


if __name__ == '__main__':
  print lambda_handler({'artist': 'Muse'}, None)
