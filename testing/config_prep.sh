#!/bin/bash -ex

rm -Rf hass-config
cp -a ../homeassistant hass-config
cp *.yaml hass-config/
rm -Rf hass-config/www

rm -Rf appdaemon-config
cp -a ../appdaemon appdaemon-config
sed -i 's|http://127.0.0.1:8123|http://hass:8123|' appdaemon-config/appdaemon.yaml
