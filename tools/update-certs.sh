#!/bin/bash

# Generates one certificate for all clementine domains and places it in
# /etc/letsencrypt/live/clementine-player.org

/root/letsencrypt/letsencrypt-auto certonly \
	-a webroot --webroot-path /var/www/clementine-player.org \
	-q \
	--renew-by-default \
	-d builds.clementine-player.org \
	-d buildbot.clementine-player.org \
	-d images.clementine-player.org \
	-d spotify.clementine-player.org

/etc/init.d/apache2 restart
