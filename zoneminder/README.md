# home-automation-configs/zoneminder

## What's Here?

* [amcrest_profile_diff.py](amcrest_profile_diff.py) - Diff Normal/Day/Night profiles from an Amcrest camera config.json file.
* [ensure_tables.py](ensure_tables.py) - Script that creates/ensures the existence of the tables used by [zmevent_handler.py](zmevent_handler.py) (for storing image analysis results) in ZoneMinder's MySQL database.
* [event_label_analysis_stats.py](event_label_analysis_stats.py) - Script to query the database for all analysis results of a given label for a given event, and print them. Used to help tune filters.
* [logrotate-zmevent_handler](logrotate-zmevent_handler) - logrotate config for [zmevent_handler.py](zmevent_handler.py)
* [statsd_utils.py](statsd_utils.py) - utility module for sending metrics to statsd
* [zm_dir_lister.py](zm_dir_lister.py) - Print information on matching event IDs.
* [zm_event_archiver.py](zm_event_archiver.py) - script I run nightly via cron; purges deleted events from the DB table populated by ``zmevent_handler.py`` and also deletes (via API) all non-archived events over 14 days old.
* [zm_frame_exporter.py](zm_frame_exporter.py) - A script using MySQL to find all Events between a set of dates, matching a specific set of criteria, and export some frames from them to a temporary directory.
* [zm_videoizer.py](zm_videoizer.py) - A script using MySQL and the ZoneMinder web UI to ensure videos exist for all events in a given timeframe (and optionally from a given monitor).
* [zmevent_comparison.py](zmevent_comparison.py) - Companion to zmevent_handler.py. Runs in a different venv with a CPU (non-GPU) version of yolo3. Runs image analysis with this analyzer on all frames that don't have it (but do from the main yolo analyzer), saves the results to the DB, and sends an email with comparison information. Mainly intended to find out, for my use case, how much worse the -tiny variant is than the normal one.
* [zmevent_config.py](zmevent_config.py) - configuration for these other modules.
* [zmevent_filters.py](zmevent_filters.py) - code for filtering out unwanted events. May be unused.
* [zmevent_handler.py](zmevent_handler.py) - Python script that I use for handling ZoneMinder events. This gets called by [zmeventnotification.pl](zmeventnotification.pl) and is where I hook in image analysis and object detection as well as passing on to HASS/AppDaemon for notifications.
* [zmevent_image_analysis.py](zmevent_image_analysis.py) - Class to run ZoneMinder event frames through darknet yolo3 for object detection.
* [zmevent_models.py](zmevent_models.py) - Classes to retrieve Event and related information from the ZoneMinder database and represent them in the application.
* [zmevent_object_filter.py](zmevent_object_filter.py) - Base classes instantiated in ``zmevent_config.py`` for filtering out certain object detections.
* [zmeventnotification_handler.py](zmeventnotification_handler.py) - Python3 daemon which listens to zmeventnotification websocket server and starts a [zmevent_handler.py](zmevent_handler.py) process for each event that comes in.
* [zmeventnotification_handler.service](zmeventnotification_handler.service) - systemd unit file for [zmeventnotification_handler.py](zmeventnotification_handler.py)
* [zmeventnotification_secrets.ini](zmeventnotification_secrets.ini) - Secrets for zmeventnotification.pl; empty, since my setup doesn't need any.
* [zmeventnotification.ini](zmeventnotification.ini) - Config file for zmeventnotification.pl; configured for websocket server **only**.
* [zmeventnotification.pl](zmeventnotification.pl) - Version 6.0.6 of https://github.com/pliablepixels/zmeventnotification
* [zmeventnotification.service](zmeventnotification.service) - systemd unit file for [zmeventnotification.pl](zmeventnotification.pl)

__NOTE:__ I'm planning a major refactor to [zmevent_handler.py](zmevent_handler.py) and [zmevent_image_analysis.py](zmevent_image_analysis.py) in the near future, to clean them up and also integrate homeassistant.

## Installation and Dependencies

[zmevent_image_analysis.py](zmevent_image_analysis.py) uses the [Pillow PIL fork](https://pillow.readthedocs.io) for some simple image analysis and the [yolo34py](https://github.com/madhawav/YOLO3-4-Py) wrapper around [darknet yolo3](https://pjreddie.com/darknet/yolo/) for object detection. On my system, running this on a 1920x1080 image on the CPU takes about 10-12 seconds. Running on even a modest GPU takes about 1/10 of that. Note that for me (Debian 9), the ``yolo34py-gpu`` package on PyPI did not work out of the box. I needed to download and compile darknet, and then ``pip install yolo34py-gpu`` with the ``DARKNET_HOME`` environment variable set to where I setup darknet.

## Other References

You may also be interested in seeing the ["DIY / Home Automation / Security" category of my blog](http://blog.jasonantman.com/categories/diy-home-automation-security/index.html) as well as the [camera](https://blog.jasonantman.com/tags/camera/index.html), [security](https://blog.jasonantman.com/tags/security/index.html), and [homeassistant](https://blog.jasonantman.com/tags/homeassistant/index.html) tags on my blog. These all provide some higher-level overview, instructional, and narrative information about what's contained here. The current high-level overview post is [Home Automation and Security System Overview](https://blog.jasonantman.com/2018/08/home-automation-and-security-system-overview/).

## Amcrest Camera Setup

My current process for provisioning new Amcrest cameras is described below. Note that since I wrote my [Amcrest IP Camera First Impressions](https://blog.jasonantman.com/2018/05/amcrest-ip-camera-first-impressions/) blog post, I've moved to a Ubiquiti AP that supports multiple SSIDs and VLANs, and I now have all of my cameras and other IoT devices on an isolated SSID/VLAN that blocks all Internet access.

### ["ProHD" IP2M-841B](https://amcrest.com/amcrest-1080p-wifi-video-security-ip-camera-pt.html) Interior PTZ Camera

I haven't done one of these in a while, but the process should essentially be the same as below.

### [IP2M-852](https://amcrest.com/amcrest-prohd-outdoor-1080p-poe-ip-security-bullet-camera-ip67-weatherproof-1080p-1920tvl-ip2m-852ew-white.html) Exterior 1080p Camera

I now have three of these; two are the IP2M-852W models which have WiFi and wired Ethernet and 12V power. It turns out that these are all placed at the fringes of my WiFi coverage area, so I ended up having to run wired Ethernet to them... which is a pain because they also require separate 12VDC power. My third and newest is the IP2M-852EW model which uses PoE. All the ones I get in the future will be PoE powered and using wired Ethernet, and I really wish I'd just gotten the wired ones to begin with.

1. Get the wired MAC address of the camera from the label on it. If there isn't a label, plug in to my laptop with a crossover cable and Wireshark running; power on the camera and record the wired Ethernet MAC address for the camera. Then power off the camera.
2. On my [VyOS](http://www.vyos.io/) router, assign the camera's wired MAC a static IP in the IoT subnet and local DNS.
3. Plug the camera in to my switch and power it on. Wait a few minutes and then access the builtin HTTP web interface at the IP I assigned.
4. Log in with the default username/password (admin/admin) and change the password.
5. Browse through the "setup" portion of the UI and record some of the current/default settings and information:
   1. "Information" -> "Version" - record all versions
   2. "Camera" -> "Video"
      * Video tab
        * Set main stream to H.264H 1080P, 10 FPS, CBR, bit rate 4096, watermark to camera hostname
        * Set sub stream to MJPEG, VGA, 10 FPS, bit rate 1024
      * Overlay tab
        * Set Channel Title to the name of the camera (ZM input)
        * Set Logo Overlay to disabled
   3. "Camera" -> "Audio" (on ProHD) - record stream information
   4. "Network" -> "TCP/IP" - change hostname; record wireless MAC; disable P2P
   5. "Network" -> "Connection" - record all ports; ensure ONVIF authentication is enabled
   6. "Network" -> ("DDNS", "IP Filter", "SMTP", "UPnP") - ensure all are disabled
   7. "Network" -> "SNMP" (if present) - enable v1
   8. "Network" -> ("Bonjour", "Multicast", "802.1x", "QoS", "HTTPs") - ensure all are disabled
   9. "System" -> "General" -> "Date & Time" - enable NTP
   10. "System" -> "Export" - export a configuration file and save it.
   11. "Event" - disable all of them for now
6. Place the new camera and wire it (if needed).
7. Add the new camera to various configurations of mine:
  * My nightly ``network_backups.sh`` script to backup the configuration and information about the camera
  * [/appdaemon/apps/alarm_handler.py](/appdaemon/apps/alarm_handler.py) ``AWAY_CAMERA_ENTITIES`` and ``CAMERA_IMAGE_ENTITIES``
  * If needed, [/appdaemon/apps/zmevent_alarm_handler.py](/appdaemon/apps/zmevent_alarm_handler.py) ``HOME_IGNORE_MONITORS``
  * [/homeassistant/configuration.yaml](/homeassistant/configuration.yaml) ``logbook -> exclude -> entities`` and a ``silence_monitor_ZM-MONITOR-NAME`` input boolean
  * [/homeassistant/ui-lovelace.yaml](/homeassistant/ui-lovelace.yaml) - entries similar to the other monitors
8. Add as a monitor in ZM and configure similarly to the others; set up zones and motion detection.
9. Once motion detection starts running and alerting, add ``IgnoredObject`` instances to [/zoneminder/zmevent_config.py](/zoneminder/zmevent_config.py) ``IGNORED_OBJECTS`` as needed.

After that, I added the wireless MAC address for the camera to my access point's ACL and then set up a static IP, local DNS, and outbound traffic reject the same way I did for the wired MAC. I then configured the WiFi connection in the camera's Setup UI, ensured it connected to the network properly, and unplugged the wired Ethernet.

### [IP8M-2496EB](https://amcrest.com/amcrest-ultrahd-4k-8mp-bullet-poe-ip-camera-security-3840x2160-131ft-nightvision-2-8mm-lens-ip67-weatherproof-microsd-recording-black-ip8m-2496eb.html) Exterior 4K/8MP Camera

1. Get the wired MAC address of the camera from the label on it.
2. On my [Ubiquiti](https://www.ubnt.com/) router, assign the camera's wired MAC a static IP in the IoT subnet and local DNS.
3. Plug the camera in to my switch and power it on. Wait a few minutes and then access the builtin HTTP web interface at the IP I assigned.
4. Log in with the default username/password (admin/admin) and change the password.
5. Browse through the "setup" portion of the UI and record some of the current/default settings and information:
   1. "Information" -> "Version" - record all versions
      * Software Version: ``V2.622.00AC000.0.R, Build Date: 2020-10-22``
      * WEB Version: ``V3.2.1.677800``
      * ONVIF Version: ``16.12(V2.4.3.651299)``
   2. "Camera" -> "Video"
      * Video tab
        * Set main stream to H.264H 2304*1296, 20 FPS, VBR, Quality 6(Best) Max Bit Rate 10240, watermark to camera hostname
        * Set sub stream to MJPEG, VGA, 8 FPS, bit rate 1024
      * Overlay tab
        * Set Channel Title to the name of the camera (ZM input)
        * Set Logo Overlay to disabled
   3. "Network" -> "TCP/IP" - change hostname; record wireless MAC; disable P2P
   4. "Network" -> "Port" - record all ports
   5. "Network" -> ("DDNS", "IP Filter", "SMTP", "UPnP") - ensure all are disabled (including UPnP "Start Device Discover")
   7. "Network" -> "HTTPs" - ensure disabled
   8. "System" -> "General" -> "Date & Time" - enable NTP, configure timezone, configure DST
   9. "System" -> "Export" - export a configuration file and save it.
   10. "Event" - disable all of them for now
6. Place the new camera and wire it (if needed).
7. Add the new camera to various configurations of mine:
  * My nightly ``network_backups.sh`` script to backup the configuration and information about the camera
  * [/appdaemon/apps/alarm_handler.py](/appdaemon/apps/alarm_handler.py) ``AWAY_CAMERA_ENTITIES`` and ``CAMERA_IMAGE_ENTITIES``
  * If needed, [/appdaemon/apps/zmevent_alarm_handler.py](/appdaemon/apps/zmevent_alarm_handler.py) ``HOME_IGNORE_MONITORS``
  * [/homeassistant/configuration.yaml](/homeassistant/configuration.yaml) ``logbook -> exclude -> entities`` and a ``silence_monitor_ZM-MONITOR-NAME`` input boolean
  * [/homeassistant/ui-lovelace.yaml](/homeassistant/ui-lovelace.yaml) - entries similar to the other monitors
8. Add as a monitor in ZM and configure similarly to the others; set up zones and motion detection.
9. Once motion detection starts running and alerting, add ``IgnoredObject`` instances to [/zoneminder/zmevent_config.py](/zoneminder/zmevent_config.py) ``IGNORED_OBJECTS`` as needed.

### [IP8M-2496EW-V2](https://amcrest.com/4k-poe-camera-bullet-ai-ip8m-2493ew-v2.html) Exterior 4K/8MP Camera

1. Plug the camera into a 12VDC power supply and the Ethernet port on my laptop; use Wireshark to get the camera's MAC address.
2. On my [Ubiquiti](https://www.ubnt.com/) router, assign the camera's wired MAC a static IP in the IoT subnet and local DNS.
3. Plug the camera in to my switch and power it on. Wait a few minutes and then access the builtin HTTP web interface at the IP I assigned.
4. Log in with the default username/password (admin/admin) and change the password.
5. Browse through the "setup" portion of the UI and record some of the current/default settings and information:
   1. "Information" -> "Version" - record all versions
      * Software Version: ``V2.800.00AC001.0.R, Build Date: 2021-07-12``
      * WEB Version: ``V3.2.1.880675``
      * ONVIF Version: ``19.06(V2.6.1.845551)``
   2. "Camera" -> "Video"
      * Video tab
        * Set main stream to H.264 3840x2160, 12 FPS, CBR, Quality 6(Best) Bit Rate 8192, watermark to camera hostname (note: see [this Amcrest forum post](https://amcrest.com/forum/viewtopic.php?f=18&t=15537) for why not to set a lower resolution)
        * Set sub stream to MJPEG, VGA, 8 FPS, bit rate 1024
      * Overlay tab
        * Set Channel Title to the name of the camera (ZM input)
        * Set Logo Overlay to disabled
   3. "Camera" -> "Configuration"
      * Profile Management tab
        * Profile Management -> General
      * Configuration tab
        * General profile
          * Leave everything defaults except "BLC Mode" - Set to Mode WDR and slider to middle (50)
   4. "Network" -> "TCP/IP" - change hostname; record wireless MAC; disable P2P
   5. "Network" -> "Connection" - record all ports
   6. "Network" -> ("DDNS", "IP Filter", "SMTP", "UPnP") - ensure all are disabled
   7. "Network" -> "HTTPs" - ensure disabled
   8. "System" -> "General" -> "Date & Time" - enable NTP, configure timezone, configure DST
   9. "System" -> "Export" - export a configuration file and save it.
   10. "Event" - disable all of them for now
6. Place the new camera and wire it (if needed).
7. Add the new camera to various configurations of mine:
  * My nightly ``network_backups.sh`` script to backup the configuration and information about the camera
  * [/appdaemon/apps/alarm_handler.py](/appdaemon/apps/alarm_handler.py) ``AWAY_CAMERA_ENTITIES`` and ``CAMERA_IMAGE_ENTITIES``
  * If needed, [/appdaemon/apps/zmevent_alarm_handler.py](/appdaemon/apps/zmevent_alarm_handler.py) ``HOME_IGNORE_MONITORS``
  * [/homeassistant/configuration.yaml](/homeassistant/configuration.yaml) ``logbook -> exclude -> entities`` and a ``silence_monitor_ZM-MONITOR-NAME`` input boolean
  * [/homeassistant/ui-lovelace.yaml](/homeassistant/ui-lovelace.yaml) - entries similar to the other monitors
8. Add as a monitor in ZM and configure similarly to the others; set up zones and motion detection.
9. Once motion detection starts running and alerting, add ``IgnoredObject`` instances to [/zoneminder/zmevent_config.py](/zoneminder/zmevent_config.py) ``IGNORED_OBJECTS`` as needed.

### Aspect Ratios

```
3840	2160	0.5625
3072	2048	0.666666666666667
3072	1728	0.5625
2592	1944	0.75
2688	1520	0.56547619047619
2048	1536	0.75
2304	1296	0.5625
1920	1080	0.5625
1280	960	0.75
1280	720	0.5625
```

## Writing Alarm Analysis Images

### Telescreen (ZoneMinder 1.32.3)

* Ensure that the Monitor configuration has ``Storage`` -> ``Save JPEGs`` -> ``Frames + Amalysis images (if available)`` set.
* Ensure that the ZM config has ``Config`` -> ``CREATE_ANALYSIS_IMAGES`` checked.
* Analysis images will **only** be written for Zones that are configured with an Alarm Check Method of ``Blobs``!!
