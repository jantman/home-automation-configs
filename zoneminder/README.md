# home-automation-configs/zoneminder

## What's Here?

* [ensure_tables.py](ensure_tables.py) - Script that creates/ensures the existence of the tables used by [zmevent_handler.py](zmevent_handler.py) (for storing image analysis results) in ZoneMinder's MySQL database.
* [logrotate-zmevent_handler](logrotate-zmevent_handler) - logrotate config for [zmevent_handler.py](zmevent_handler.py)
* [zmevent_handler.py](zmevent_handler.py) - Python script that I use for handling ZoneMinder events. This gets called by [zmeventnotification.pl](zmeventnotification.pl) and is where I hook in image analysis and object detection as well as notifications.
* [zmevent_image_analysis.py](zmevent_image_analysis.py) - Class to run ZoneMinder event frames through darknet yolo3 for object detection.
* [zmeventnotification.pl](zmeventnotification.pl) - Simple Perl daemon based on https://github.com/pliablepixels/zmeventserver that checks ZoneMinder shared memory for new events every 3 seconds, and runs [zmevent_handler.py](zmevent_handler.py) when they are found.
* [zmeventnotification.service](zmeventnotification.service) - systemd unit file for [zmeventnotification.pl](zmeventnotification.pl)

__NOTE:__ I'm planning a major refactor to [zmevent_handler.py](zmevent_handler.py) and [zmevent_image_analysis.py](zmevent_image_analysis.py) in the near future, to clean them up and also integrate homeassistant.

## Installation and Dependencies

[zmevent_image_analysis.py](zmevent_image_analysis.py) uses the [Pillow PIL fork](https://pillow.readthedocs.io) for some simple image analysis and the [yolo34py](https://github.com/madhawav/YOLO3-4-Py) wrapper around [darknet yolo3](https://pjreddie.com/darknet/yolo/) for object detection. On my system, running this on a 1920x1080 image on the CPU takes about 10-12 seconds. Running on even a modest GPU takes about 1/10 of that. Note that for me (Debian 9), the ``yolo34py-gpu`` package on PyPI did not work out of the box. I needed to download and compile darknet, and then ``pip install yolo34py-gpu`` with the ``DARKNET_HOME`` environment variable set to where I setup darknet.
