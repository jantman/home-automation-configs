# home-automation-configs/zoneminder

## What's Here?

* [ensure_tables.py](ensure_tables.py) - Script that creates/ensures the existence of the tables used by [zmevent_handler.py](zmevent_handler.py) (for storing image analysis results) in ZoneMinder's MySQL database.
* [logrotate-zmevent_handler](logrotate-zmevent_handler) - logrotate config for [zmevent_handler.py](zmevent_handler.py)
* [zmevent_archiver.py](zmevent_archiver.py) - script I run nightly via cron; purges deleted events from the DB table populated by ``zmevent_handler.py`` and also deletes (via API) all non-archived events over 14 days old.
* [zmevent_comparison.py](zmevent_comparison.py) - Companion to zmevent_handler.py. Runs in a different venv with a CPU (non-GPU) version of yolo3. Runs image analysis with this analyzer on all frames that don't have it (but do from the main yolo analyzer), saves the results to the DB, and sends an email with comparison information. Mainly intended to find out, for my use case, how much worse the -tiny variant is than the normal one.
* [zmevent_config.py](zmevent_config.py) - configuration for these other modules.
* [zmevent_filters.py](zmevent_filters.py) - code for filtering out unwanted events. May be unused.
* [zmevent_handler.py](zmevent_handler.py) - Python script that I use for handling ZoneMinder events. This gets called by [zmeventnotification.pl](zmeventnotification.pl) and is where I hook in image analysis and object detection as well as passing on to HASS/AppDaemon for notifications.
* [zmevent_image_analysis.py](zmevent_image_analysis.py) - Class to run ZoneMinder event frames through darknet yolo3 for object detection.
* [zmevent_models.py](zmevent_models.py) - Classes to retrieve Event and related information from the ZoneMinder database and represent them in the application.
* [zmevent_object_filter.py](zmevent_object_filter.py) - Base classes instantiated in ``zmevent_config.py`` for filtering out certain object detections.
* [zmeventnotification.pl](zmeventnotification.pl) - Simple Perl daemon based on https://github.com/pliablepixels/zmeventserver that checks ZoneMinder shared memory for new events every 3 seconds, and runs [zmevent_handler.py](zmevent_handler.py) when they are found.
* [zmeventnotification.service](zmeventnotification.service) - systemd unit file for [zmeventnotification.pl](zmeventnotification.pl)
* [zm_videoizer.py](zm_videoizer.py) - A script using MySQL and the ZoneMinder web UI to ensure videos exist for all events in a given timeframe (and optionally from a given monitor)

__NOTE:__ I'm planning a major refactor to [zmevent_handler.py](zmevent_handler.py) and [zmevent_image_analysis.py](zmevent_image_analysis.py) in the near future, to clean them up and also integrate homeassistant.

## Installation and Dependencies

[zmevent_image_analysis.py](zmevent_image_analysis.py) uses the [Pillow PIL fork](https://pillow.readthedocs.io) for some simple image analysis and the [yolo34py](https://github.com/madhawav/YOLO3-4-Py) wrapper around [darknet yolo3](https://pjreddie.com/darknet/yolo/) for object detection. On my system, running this on a 1920x1080 image on the CPU takes about 10-12 seconds. Running on even a modest GPU takes about 1/10 of that. Note that for me (Debian 9), the ``yolo34py-gpu`` package on PyPI did not work out of the box. I needed to download and compile darknet, and then ``pip install yolo34py-gpu`` with the ``DARKNET_HOME`` environment variable set to where I setup darknet.
