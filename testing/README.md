# home-automation-configs/testing

This directory provides some tools and configuration related to testing my custom code on a local system instead of my actual homeassistant/appdaemon/zoneminder machine.

While I run home-assistant and appdaemon installed in virtualenvs for my real install, this uses docker for ease and simplicity. It requires [docker-compose](https://docs.docker.com/compose/).

## Usage

__Before Running docker-compose,__ run ``./config_prep.sh``.

* __Run services:__ ``docker-compose up -d``
  * HASS will be available at http://localhost:8123 from a container named "hass"
  * AppDaemon will be in a container named "appdaemon"
* __See what's running:__ ``docker-compose ps``
* __Get a shell in the HASS container:__ ``docker-compose exec hass /bin/sh``
* __Restart HASS:__ ``docker-compose restart hass``
* __View Logs:__ ``docker-compose logs [-f] [hass|appdaemon]``
* __Stop everything:__ ``docker-compose down``

Use ``state_setter.py`` to set initial states and update states. Requires ``requests``.
