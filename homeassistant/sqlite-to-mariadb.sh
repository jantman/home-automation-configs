#!/bin/bash -ex
# based on: https://gist.github.com/seidler2547/93012edf3c7a2414ec1d9a8ebbc9c1a6

read -p "Restart docker-hass to load new config file, with MySQL; stop again when setup has finished... "

# now empty the tables
mysql hass -e 'delete from events; delete from recorder_runs; delete from schema_changes; delete from states;'

# this is the actual conversion:
sqlite3 /opt/homeassistant/homeassistant/home-assistant_v2.db .dump \
| sed -re 's/^PRAGMA .+OFF/SET FOREIGN_KEY_CHECKS=0;SET UNIQUE_CHECKS=0/' \
       -e 's/^CREATE INDEX .+//' \
       -e 's/^BEGIN TRANSACTION;$/SET autocommit=0;BEGIN;/' \
       -e '/^CREATE TABLE .+ \($/,/^\);/ d' \
       -e 's/^INSERT INTO "([^"]+)"/INSERT INTO \1/' \
       -e 's/\\n/\n/g' \
| perl -pe 'binmode STDOUT, ":utf8mb4";s/\\u([0-9A-Fa-f]{4})/pack"U*",hex($1)/ge' \
| mysql hass --default-character-set=utf8mb4
