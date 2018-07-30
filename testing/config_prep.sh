#!/bin/bash -ex

rm -Rf hass-config
cp -a ../homeassistant hass-config
cp *.yaml hass-config/
