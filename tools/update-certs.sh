#!/bin/bash

# Generates one certificate for all clementine domains and places it in
# /etc/letsencrypt/live/clementine-player.org

/root/letsencrypt/letsencrypt-auto certonly \
	-a webroot --webroot-path /var/www/clementine-player.org \
	-q \
	--renew-by-default \
	-d clementine-player.org \
	-d www.clementine-player.org \
	-d builds.clementine-player.org \
	-d buildbot.clementine-player.org \
	-d data.clementine-player.org \
	-d images.clementine-player.org \
	-d spotify.clementine-player.org

/etc/init.d/apache2 restart

GOOGLE_APPLICATION_CREDENTIALS=$HOME/credentials.json \
  go run $GOPATH/src/github.com/clementine-player/Website/tools/cmd/upload_cert.go \
  -fullchain /etc/letsencrypt/live/clementine-player.org/fullchain.pem \
  -key /etc/letsencrypt/live/clementine-player.org/privkey.pem
