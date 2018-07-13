# home-automation-configs/appdaemon

This directory contains my [AppDaemon](http://appdaemon.readthedocs.io/en/latest/) configuration and apps. Documentation is in the docstring at the top of each module. Note this also contains ``sane_app_logging.py``, a helper I use to make AppDaemon logging a bit more like the built-in ``logging`` module and to control debug logging at runtime.

* [apps/alarm_handler.py](apps/alarm_handler.py) - The heart of my security system - handles arming/disarming, ensuring doors are closed before arming, listening for sensor events to trigger the alarm, sending notifications, and snapshotting security cameras if one has a view of the triggered sensor.
* [apps/sane_app_logging.py](apps/sane_app_logging.py) - Class I use to improve logging from within apps, make it a bit more Pythonic, and allow toggling debug messages on/off per-app at runtime via events.
* [apps/zwave_checker.py](apps/zwave_checker.py) - Runs daily to notify me of failed ZWave devices, or ZWave devices with low batteries.
