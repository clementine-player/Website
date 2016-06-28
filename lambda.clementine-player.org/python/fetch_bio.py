"""AWS Lambda handler to fetch an artist description from the Knowledge Graph.

Fetches a description of an artist from the Google Knowledge Graph. Uses a
schema.org type to hopefully disambiguate.

This API requires a secret key which is stored in KMS and this lambda's identity
has access.

Build instructions:
  pip install requests -t .  # Install the requests library in this directory.
  zip -r lambda.zip *  # Create a deployable zip for uploading to lambda.
"""

import base64
import boto3
import requests

API_KEY_ENCRYPTED = ('CiDbbkvFbR/FSNb67gyuZaEakCDysQrQU2Rl3aUFOK/jkRKvAQEBAgB42'
                     '25LxW0fxUjW+u4MrmWhGpAg8rEK0FNkZd2lBTiv45EAAACGMIGDBgkqhk'
                     'iG9w0BBwagdjB0AgEAMG8GCSqGSIb3DQEHATAeBglghkgBZQMEAS4wEQQ'
                     'Mpr+DxuzD6soM3enSAgEQgEJIMPYKWJ1tR8drlgqEYBekZuSTcHrxzx1X'
                     'Yh9MkeVwIzhfPWqgL8uWKAJnaNdZqlss1P6l+peSkmO2TLFOHUVLwQM=')

KG_URL = 'https://kgsearch.googleapis.com/v1/entities:search'


def fetch_bio(event, context):
  client = boto3.client('kms')
  response = client.decrypt(
      CiphertextBlob=base64.b64decode(API_KEY_ENCRYPTED))
  api_key = response['Plaintext']

  response = requests.get(KG_URL, {
      'query': event['artist'],
      'limit': '1',
      'types': 'MusicGroup',  # schema.org type
      'key': api_key,
      'languages': event['lang'],
  })

  items = response.json()['itemListElement']
  result = items[0]['result']
  return result['detailedDescription']
