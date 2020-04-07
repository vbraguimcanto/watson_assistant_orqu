#!/bin/sh

echo "Starting uwsgi reverse proxy..."

uwsgi --ini uwsgi.ini
