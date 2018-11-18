#!/bin/bash -ex

rm -Rf hass-config
cp -a ../homeassistant hass-config
cp *.yaml hass-config/
sed -i 's/192.168.0.24/192.168.0.99/g' hass-config/configuration.yaml
sed -i 's/localhost/192.168.0.102/g' hass-config/configuration.yaml

rm -Rf appdaemon-config
cp -a ../appdaemon appdaemon-config
sed -i 's|http://127.0.0.1:8123|http://hass:8123|' appdaemon-config/appdaemon.yaml
