"""
I have two really cheap cameras from Amazon, "UnionCam Q5" and "UnionCam Q2".
They work acceptably well for indoor cameras to keep an eye on my pets,
especially given their $25USD price point. They do have a few downsides though:

- they lack a real-time clock
- they don't support NTP (even though they tell ONVIF they do)
- you can't turn off the timestamp overlay on the video

As a result, whenever they receive power, their timestamp overlay starts
counting up from the Unix epoch - 1970-01-01 00:00:00.

Given a list of the IPs or hostnames of such cameras, this script connects to
each one over ONVIF and sets the current time on them. It runs every hour.
"""

import logging
import datetime
import time
import appdaemon.plugins.hass.hassapi as hass
from onvif import ONVIFCamera
from tzlocal import get_localzone

from sane_app_logging import SaneLoggingApp

#: list of UnionCam hosts or IPs to set time on
CAMERA_HOSTS = [
    'UnionCamQ2-1',
    'UnionCamQ5-1'
]

#: Whether or not camera should automatically adjust for daylight savings time
ADJUST_FOR_DST = True

#: Default for info-as-debug logging via LogWrapper; can be overridden
#: at runtime via events. See ``sane_app_logging.py``.
LOG_DEBUG = False


def get_timezone_string():
    """
    While the ONVIF specification says TimeZone should be specified in
    POSIX 1003.1, the UnionCams don't use that. Find the local timezone and then
    generate a TZ string to send to the camera in the "name-offset" format that
    it expects (i.e. for the America/New_York TZ, "EST-5:00:00").
    """
    now = datetime.datetime.now()
    tz = get_localzone()
    name = tz.tzname(now)
    offset = tz.utcoffset(now)
    secs = offset.total_seconds()
    hours = int(secs / 3600.0)
    secs = secs % 3600.0
    mins = int(secs / 60.0)
    secs = int(secs % 60.0)
    return '{0:}{1:d}:{2:0>2d}:{3:0>2d}'.format(name, hours, mins, secs)


class UnionCamTimeSetter(hass.Hass, SaneLoggingApp):

    def initialize(self):
        self._setup_logging(self.__class__.__name__, LOG_DEBUG)
        self._log.info("Initializing UnionCamTimeSetter...")
        self.run_hourly(self._set_times, datetime.time(0, 12, 0))
        self._log.info('Done initializing UnionCamTimeSetter')
        self.listen_event(self._set_times, event='UNIONCAM_TIME_SETTER')

    def _set_times(self, *args, **kwargs):
        tz = get_timezone_string()
        self._log.info(
            'Setting date/time on UnionCam Cameras (timezone: %s)...', tz
        )
        dt = datetime.datetime.now()
        for host in CAMERA_HOSTS:
            self._log.info('Connecting to camera: %s', host)
            mycam = ONVIFCamera(host, 8090, 'admin', '123456')
            curr = mycam.devicemgmt.GetSystemDateAndTime()
            time_params = mycam.devicemgmt.create_type('SetSystemDateAndTime')
            time_params.DateTimeType = 'Manual'
            time_params.DaylightSavings = ADJUST_FOR_DST
            curr.TimeZone.TZ = tz
            time_params.TimeZone = curr.TimeZone
            curr.UTCDateTime.Date.Year = dt.year
            curr.UTCDateTime.Date.Month = dt.month
            curr.UTCDateTime.Date.Day = dt.day
            curr.UTCDateTime.Time.Hour = dt.hour
            curr.UTCDateTime.Time.Minute = dt.minute
            curr.UTCDateTime.Time.Second = dt.second
            time_params.UTCDateTime = curr.UTCDateTime
            mycam.devicemgmt.SetSystemDateAndTime(time_params)
        self._log.info('Done setting UnionCam date/time.')
