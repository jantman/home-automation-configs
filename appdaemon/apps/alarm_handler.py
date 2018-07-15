"""
This is my alarm_handler app, the heart of one half of my HASS-based security
system (the other part is based on ZoneMinder).

All configuration is in constants near the top of the file.

# Dependencies

- requests, which appdaemon should provide
- PIL for image manipulation; I install via [pillow](https://pillow.readthedocs.io/)

# Important Notes

- This script retrieves secrets directly from the HASS ``secrets.yaml`` file.
The user it runs as must be able to read that file. The path to the HASS
configuration directory is read from the HASS API in
``AlarmHandler._get_hass_secrets()`` via the ``conf_dir`` key of the return
value of ``appdaemon.plugins.hass.hassapi.Hass.get_hass_config()`` and then
``secrets.yaml`` in that file is read and loaded. The expected secrets.yaml
keys are defined in ``AlarmHandler._get_hass_secrets()``.

- I have 3 fixed security cameras and one indoor PTZ camera. The code around
snapshotting these cameras is specific to my setup, and could use to be made
more general/configurable.

# Highly Custom Bits

- Optional control of Amcrest camera PTZ
- Notifications via Pushover (direct to API, for image attachments)
- Attach ZoneMinder snapshot images to notifications if applicable.

# Features

- 3-state alarm: Disarmed, Home, Away. Home triggers on exterior (i.e. door /
  window) sensors only, Away also triggers on interior (i.e. motion) sensors.
- ZoneMinder RunState is also updated to match the alarm state.
- Alarm state set based on manual input_select in UI or device tracker. If the
  device_tracker entity_id for my phone (configurable) enters the "Home" zone,
  disarm the alarm. If it leaves the "Home" zone, arm it as Away.
- Listens for an event, ``CUSTOM_ALARM_STATE_SET``, to set the state. Event data
  is a ``state`` key with possible values the same as the input_select options.
- If alarm is triggered, all lights come on for 10-20 minutes and Pushover alert
  is sent.
- If there is a ZoneMinder camera pointed at the location of the alarm event
  (configurable), a snapshot is sent with the Pushover alert. This can also
  handle moving an Amcrest PTZ camera, and combining two images for a view of
  both sides of a door/window.
- Pushover notification on arming/disarming.
- Ensure all doors/windows are closed before arming.

"""

import re
import logging
import os
import requests
from requests.auth import HTTPDigestAuth
from PIL import Image
from io import BytesIO
from random import randint
import appdaemon.plugins.hass.hassapi as hass

from yaml import load as load_yaml
try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper

from sane_app_logging import SaneLoggingApp

#: List of regular expressions to match the binary_sensor entities for my
#: "exterior" zone, i.e. things that alarm when I'm either Home or Away
EXTERIOR_SENSOR_REs = [
    re.compile(r'^binary_sensor\.ecolink_doorwindow_sensor_sensor.*$')
]

#: List of regular expressions to match the binary_sensor entities for my
#: "interor" zone, i.e. things that alarm only when I'm Away.
INTERIOR_SENSOR_REs = [
    re.compile(r'^binary_sensor\.ecolink_motion_detector_sensor.*$'),
    re.compile(r'^binary_sensor\..*_motion$')
]

#: Device tracker entity ID for my phone, for arming/disarming based on
#: presence or proximity.
DEVICE_TRACKER_ENTITY = 'device_tracker.02157df2c2d6e627'

#: Entity ID for the input_select that controls the alarm state. This should
#: have three options for the three possible alarm states: Home, Away, and
#: Disarmed. The option strings are defined in the following constants.
ALARM_STATE_SELECT_ENTITY = 'input_select.alarmstate'
HOME = 'Home'
AWAY = 'Away'
DISARMED = 'Disarmed'

#: List of entity IDs that should be turned on for 10 minutes after an alarm.
LIGHT_ENTITIES = [
    # Kitchen
    'light.linear_lb60z1_dimmable_led_light_bulb_level',
    'light.linear_lb60z1_dimmable_led_light_bulb_level_2',
    # Porch
    'light.linear_lb60z1_dimmable_led_light_bulb_level_3',
    # TV
    'switch.livingroomlight_switch'
]

#: List of RGB light entities that should react to an alarm. Right now they
#: act the same way as LIGHT_ENTITIES, but at some point I may make them flash
#: colors.
RGB_LIGHT_ENTITIES = [
    'light.zipato_bulb_2_level',  # Porch
]

#: If an alarm is triggered based on state change of one of these entity IDs,
#: a snapshot from the specified ZoneMinder Monitor ID will be attached.
#: The second argument specifies a PTZ ID to move PTZ_MONITOR_ID to before
#: snapshotting it. If the Monitor ID is not PTZ_MONITOR_ID, a snapshot of
#: both the first element (Monitor ID) and PTZ_MONITOR_ID panned to the PTZ
#: preset will be included, side by side in one image.
CAMERA_IMAGE_ENTITIES = {
    'binary_sensor.kitchen_motion': (2, 2),
    'binary_sensor.livingroom_motion': (2, 1),
    'binary_sensor.ecolink_doorwindow_sensor_sensor_2': (5, None),  # crawlspace
    'binary_sensor.ecolink_doorwindow_sensor_sensor_3': (5, None),  # gate
    'binary_sensor.ecolink_doorwindow_sensor_sensor_4': (4, 2),  # kitchen
    'binary_sensor.ecolink_doorwindow_sensor_sensor': (3, 1)  # front door
}

#: The ID of the ZoneMinder monitor with PTZ support, for the above.
PTZ_MONITOR_ID = 2

#: The hostname or IP address of the Amcrest PTZ camera.
PTZ_CAM_HOST = '192.168.0.61'

#: Default for info-as-debug logging via LogWrapper; can be overridden
#: at runtime via events. See ``sane_app_logging.py``.
LOG_DEBUG = False


def fmt_entity(entity, kwargs):
    """
    Format the provided entity for printing. If ``friendly_name`` is in
    ``kwargs``, return a string that includes it.

    :param entity: Entity ID
    :type entity: str
    :param kwargs: HASS event kwargs
    :type kwargs: dict
    :returns: formatted entity name
    :rtype: str
    """
    if 'friendly_name' in kwargs:
        return '%s (%s)' % (entity, kwargs['friendly_name'])
    return entity


class AlarmHandler(hass.Hass, SaneLoggingApp):
    """
    AlarmHandler AppDaemon app.

    This essentially does what the HASS Manual Alarm Control Panel would do,
    except much simpler and without the state machine because I use presence
    detection and a manual input_select for arming/disarming.
    """

    def initialize(self):
        """
        Initialize the AlarmHandler

        Setup logging and some instance variables. Get secrets from HASS
        ``secrets.yaml``. Then find all the entities we care about (sensors,
        device tracker, and the input_select for alarm state) from the HASS API
        and setup listeners for them.
        """
        self._setup_logging(self.__class__.__name__, LOG_DEBUG)
        self._log.info("Initializing AlarmHandler...")
        #: store state of lights when turned on by alarm, so we can set them
        #: back how they were after some timeout
        self._light_states = {}
        self._hass_secrets = self._get_hass_secrets()
        #: dict of entity_id to friendly_name for all sensors that make up
        #: the "interior" zone; populated by :py:meth:`~._states_to_listen_for`
        self._interior_sensors = {}
        #: dict of entity_id to friendly_name for all sensors that make up
        #: the "exterior" zone; populated by :py:meth:`~._states_to_listen_for`
        self._exterior_sensors = {}
        # self._states_to_listen_for() populates self._interior_sensors and
        # self._exterior_sensors
        listen_to = self._states_to_listen_for()
        self._log.debug('Interior entities: %s', self._interior_sensors)
        self._log.debug('Exterior entites: %s', self._exterior_sensors)
        # setup listeners for interior sensors
        for eid, friendly_name in self._interior_sensors.items():
            self._log.debug(
                'listen_state(self._handle_state_interior, entity="%s", '
                'friendly_name="%s", new="on")', eid, friendly_name
            )
            self.listen_state(
                self._handle_state_interior, eid, friendly_name=friendly_name,
                new="on"
            )
        # setup listeners for exterior sensors
        for eid, friendly_name in self._exterior_sensors.items():
            self._log.debug(
                'listen_state(self._handle_state_exterior, entity="%s", '
                'friendly_name="%s", new="on")', eid, friendly_name
            )
            self.listen_state(
                self._handle_state_exterior, eid, friendly_name=friendly_name,
                new="on"
            )
        # setup listener for the input_select change
        self._log.debug('listen_state("%s")', ALARM_STATE_SELECT_ENTITY)
        self.listen_state(
            self._input_alarmstate_change, ALARM_STATE_SELECT_ENTITY
        )
        # setup listener for device tracker state change
        self._log.debug('listen_state("%s")' % DEVICE_TRACKER_ENTITY)
        self.listen_state(
            self._device_tracker_change, DEVICE_TRACKER_ENTITY
        )
        # setup listener for CUSTOM_ALARM_STATE_SET event
        self._log.debug('listen_event(CUSTOM_ALARM_STATE_SET)')
        self.listen_event(
            self._handle_state_set_event, event='CUSTOM_ALARM_STATE_SET'
        )
        self._log.info('Done initializing AlarmHandler')

    @property
    def alarm_state(self):
        """Return the string state of the alarm_state input select."""
        return self.get_state(ALARM_STATE_SELECT_ENTITY)

    def _states_to_listen_for(self):
        """
        Return a list of all entities to listen for state changes on, and
        also populate instance variables.

        Iterate over every element in HASS's current state as returned by
        :py:meth:`~.get_state`. For elements that match a regex in
        :py:const:`~.EXTERIOR_SENSOR_REs`, add them to
        :py:attr:`~._exterior_sensors`. For elements that didn't match that but
        match :py:const:`~.INTERIOR_SENSOR_REs`, add them to
        :py:attr:`~._interior_sensors`. Return a list of all string entity IDs
        added to either of those.
        """
        all_entities = {}
        for e in self.get_state().values():
            if e is None:
                continue
            all_entities[e['entity_id']] = e.get(
                'attributes', {}
            ).get('friendly_name', e['entity_id'])
        self._log.debug('All entities: %s', all_entities)
        listen_entities = []
        for eid, friendly_name in all_entities.items():
            matched = False
            for r in EXTERIOR_SENSOR_REs:
                if r.match(eid):
                    listen_entities.append(eid)
                    self._exterior_sensors[eid] = friendly_name
                    matched = True
                    break
            if matched:
                continue
            for r in INTERIOR_SENSOR_REs:
                if r.match(eid):
                    listen_entities.append(eid)
                    self._interior_sensors[eid] = friendly_name
                    break
        self._log.debug('Entities to listen to: %s', listen_entities)
        return listen_entities

    def _get_hass_secrets(self):
        """
        Return the dictionary contents of HASS ``secrets.yaml``.
        """
        # get HASS configuration from its API
        apiconf = self.get_hass_config()
        # formulate the absolute path to HASS secrets.yaml
        conf_path = os.path.join(apiconf['config_dir'], 'secrets.yaml')
        self._log.debug('Reading hass secrets from: %s', conf_path)
        # load the YAML
        with open(conf_path, 'r') as fh:
            conf = load_yaml(fh, Loader=Loader)
        self._log.debug('Loaded secrets.')
        # verify that the secrets we need are present
        assert 'pushover_api_key' in conf
        assert 'pushover_user_key' in conf
        assert 'amcrest_username' in conf
        assert 'amcrest_password' in conf
        # return the full dict
        return conf

    def _handle_state_interior(self, entity, attribute, old, new, kwargs):
        """Handle change to interior sensors, i.e. motion sensors."""
        self._log.debug(
            'Got _handle_state_interior callback; entity=%s attribute=%s '
            'old=%s new=%s kwargs=%s' , entity, attribute, old, new, kwargs
        )
        # just to make this method more concise
        a_state = self.alarm_state
        # If alarm isn't in AWAY state, disregard this event
        if a_state != AWAY:
            self._log.info(
                'Alarm state %s; disregarding interior state change '
                '(%s %s from %s to %s)', a_state,
                fmt_entity(entity, kwargs), attribute, old, new
            )
            return
        # Assign a friendly name to the state: on -> Detected, off -> Cleared
        st_name = 'Detected'
        if new == 'off':
            st_name = 'Cleared'
        # if the entity has a friendly_name, use that; otherwise use entity ID
        e_name = entity
        if 'friendly_name' in kwargs:
            e_name = kwargs['friendly_name']
        # Add event/trigger to logbook
        self.call_service(
            'logbook/log', name='Alarm Triggered (%s)' % a_state,
            message='Interior zone - %s %s changed from %s to %s' % (
                fmt_entity(entity, kwargs), attribute, old, new
            )
        )
        # If we have a camera pointing (or point-able via PTZ) at this sensor,
        # get the image from it to include in our notification.
        image = None
        if entity in CAMERA_IMAGE_ENTITIES.keys():
            mon_id, preset = CAMERA_IMAGE_ENTITIES[entity]
            image = self._image_for_camera(mon_id, ptz_preset=preset)
        self._do_notify_pushover(
            'ALARM: %s %s' % (e_name, st_name),
            'System is in state %s; %s %s changed from %s to %s' % (
                a_state, fmt_entity(entity, kwargs), attribute, old, new
            ),
            image=image, sound='alien'
        )
        self._do_alarm_lights()

    def _handle_state_exterior(self, entity, attribute, old, new, kwargs):
        """Handle change to exterior sensors, i.e. door/window sensors"""
        self._log.debug(
            'Got _handle_state_exterior callback; entity=%s attribute=%s '
            'old=%s new=%s kwargs=%s', entity, attribute, old, new, kwargs
        )
        a_state = self.alarm_state
        if a_state not in [HOME, AWAY]:
            self._log.warning(
                'Alarm state %s; disregarding interior state '
                'change (%s %s from %s to %s)', a_state,
                fmt_entity(entity, kwargs), attribute, old, new
            )
            return
        # friendly name of the state name
        st_name = 'open'
        if new == 'off':
            st_name = 'closed'
        # friendly name of the entity, if it has one
        e_name = entity
        if 'friendly_name' in kwargs:
            e_name = kwargs['friendly_name']
        self.call_service(
            'logbook/log', name='Alarm Triggered (%s)' % a_state,
            message='Exterior zone - %s %s changed from %s to %s' % (
                fmt_entity(entity, kwargs), attribute, old, new
            )
        )
        # If we have a camera pointing (or point-able via PTZ) at this sensor,
        # get the image from it to include in our notification.
        image = None
        if entity in CAMERA_IMAGE_ENTITIES.keys():
            mon_id, preset = CAMERA_IMAGE_ENTITIES[entity]
            image = self._image_for_camera(mon_id, ptz_preset=preset)
        self._do_notify_pushover(
            'ALARM: %s %s' % (e_name, st_name),
            'System is in state %s; %s %s changed from %s to %s' % (
                a_state, fmt_entity(entity, kwargs), attribute, old, new
            ),
            image=image, sound='alien'
        )
        self._do_alarm_lights()

    def _handle_state_set_event(self, event_name, data, _):
        """
        Handle the CUSTOM_ALARM_STATE_SET event.

        event type: LOGWRAPPER_SET_DEBUG
        data: dict with one key, ``state``. String value must match the value
        of one of :py:const:`~.HOME`, :py:const:`~.AWAY` or
        :py:const:`~.DISARMED`.
        """
        self._log.debug('Got %s event data=%s', event_name, data)
        if event_name != 'CUSTOM_ALARM_STATE_SET':
            self._log.error(
                'Got event of improper type: %s', event_name
            )
            return
        state = data.get('state', None)
        if state not in [HOME, AWAY, DISARMED]:
            self._log.error(
                'Got invalid state for CUSTOM_ALARM_STATE_SET event: %s',
                state
            )
            return
        if state == HOME:
            self._log.info('Arming HOME from event')
            self._arm_home(self.get_state(ALARM_STATE_SELECT_ENTITY))
            return
        if state == AWAY:
            self._log.info('Arming AWAY from event')
            self._arm_away(self.get_state(ALARM_STATE_SELECT_ENTITY))
            return
        self._log.info('Disarming from event')
        self._disarm(self._get_state(ALARM_STATE_SELECT_ENTITY))

    def _do_alarm_lights(self):
        """
        Turn on all lights when alarm goes off. Save state of all lights before
        turning on, and revert them 10-20 minutes later.
        """
        self._log.info('Turning on all lights')
        for e_id in LIGHT_ENTITIES + RGB_LIGHT_ENTITIES:
            self._light_states[e_id] = self.get_state(entity=e_id)
            self.turn_on(e_id)
        self._log.info(
            'All lights turned on. Previous state: %s', self._light_states
        )
        # revert the lights somewhere from 10 to 20 minutes later
        undo_delay = randint(600, 1200)
        self._log.info(
            'Scheduling _undo_alarm_lights in %d seconds', undo_delay
        )
        self.run_in(self._undo_alarm_lights, undo_delay)

    def _undo_alarm_lights(self, _):
        """Revert lights back to previous state, 10-20 min. after alarm."""
        self._log.info('Reverting all lights to previous state')
        for e_id, prev_state in self._light_states.items():
            if prev_state == 'off':
                self.turn_off(e_id)
            # else it was on before, leave it on
        self._log.info('Done reverting light state')

    def _input_alarmstate_change(self, entity, attribute, old, new, kwargs):
        """Arm or disarm the alarm based on the alarmstate input_select."""
        self._log.debug(
            '_input_alarmstate_change callback; entity=%s attribute=%s '
            'old=%s new=%s kwargs=%s', entity, attribute, old, new, kwargs
        )
        if new == 'Away':
            self._arm_away(old)
        elif new == 'Home':
            self._arm_home(old)
        elif new == 'Disarmed':
            self._disarm(old)
        else:
            raise RuntimeError('Unknown new state: %s' % new)

    def _device_tracker_change(self, entity, attribute, old, new, kwargs):
        """Arm or disarm the alarm based on device tracker state."""
        old = old.lower()
        new = new.lower()
        self._log.debug(
            '_device_tracker_change callback; entity=%s attribute=%s '
            'old=%s new=%s kwargs=%s', entity, attribute, old, new, kwargs
        )
        if old == new:
            self._log.debug(
                'Ignoring device tracker state unchanged (%s)', old
            )
            return
        if old == 'home':
            self._log.info(
                'Device tracker went from Home to %s; Arm system in Away mode',
                new
            )
            self.select_option(ALARM_STATE_SELECT_ENTITY, 'Away')
        elif new == 'home':
            self._log.info(
                'Device tracker went from %s to Home; disarm system', old
            )
            self.select_option(ALARM_STATE_SELECT_ENTITY, 'Disarmed')
        else:
            self._log.warning(
                'Device tracker broadcast unknown state transition: '
                'attribute=%s old=%s new=%s', attribute, old, new
            )

    def _arm_home(self, prev_state):
        """Ensure exterior sensors are closed and then arm system in Home."""
        self._log.info('Arming in Home mode (previous state: %s)', prev_state)
        open_doors = self._exterior_doors_open()
        if len(open_doors) > 0:
            self._log.warning('Cannot arm Home; open doors: %s', open_doors)
            self._do_notify_pushover(
                'ARMING FAILURE - Doors Open',
                'System requested arming to Home state, but the following '
                'exterior doors are currently open, so the system is '
                'remaining in %s state: %s' % (prev_state, open_doors),
                sound='falling'
            )
            self.select_option(ALARM_STATE_SELECT_ENTITY, prev_state)
            return
        self._do_notify_pushover(
            'System Armed - Home',
            'System has been armed in "Home" mode. All exterior sensors '
            'secure.', sound='gamelan'
        )
        self._log.info('Setting ZoneMinder runstate to Home')
        self.call_service('zoneminder/set_run_state', name='Home')

    def _arm_away(self, prev_state):
        """Ensure exterior sensors are closed and then arm system in Away."""
        self._log.info('Arming in Away mode (previous state: %s)', prev_state)
        open_doors = self._exterior_doors_open()
        if len(open_doors) > 0:
            self._log.warning('Cannot arm Away; open doors: %s', open_doors)
            self._do_notify_pushover(
                'ARMING FAILURE - Doors Open',
                'System requested arming to Away state, but the following '
                'exterior doors are currently open, so the system is '
                'remaining in %s state: %s' % (prev_state, open_doors),
                sound='falling'
            )
            self.select_option(ALARM_STATE_SELECT_ENTITY, prev_state)
            return
        self._do_notify_pushover(
            'System Armed - Away',
            'System has been armed in "Away" mode. All exterior sensors '
            'secure.', sound='gamelan'
        )
        self._log.info('Setting ZoneMinder runstate to Home')
        self.call_service('zoneminder/set_run_state', name='Away')

    def _disarm(self, prev_state):
        """Disarm the system."""
        self._log.info('Disarming system (previous state: %s)', prev_state)
        self._do_notify_pushover(
            'System Disarmed',
            'System has been disarmed.'
        )
        self._log.info('Setting ZoneMinder runstate to Monitor')
        self.call_service('zoneminder/set_run_state', name='Monitor')

    def _exterior_doors_open(self):
        """Return a list of the friendly_name of any open exterior sensors."""
        opened = []
        for eid, friendly_name in self._exterior_sensors.items():
            if self.get_state(eid) == 'on':
                opened.append(friendly_name)
        return opened

    def _image_for_camera(self, monitor_id, ptz_preset=None):
        """
        Retrieve an image for the specified camera(s).

        - If ``ptz_preset`` is not specified, return the return value of
          :py:meth:`~._get_camera_capture` for ``monitor_id``.
        - If ``ptz_preset`` is specified and ``monitor_id`` is
          ``PTZ_MONITOR_ID``, call :py:meth:`~._ptz_to` to move the camera and
          then return the return value of :py:meth:`~._get_camera_capture` for
          ``monitor_id``.
        - If ``ptz_preset`` is specified and ``monitor_id`` is NOT
          ``PTZ_MONITOR_ID``, then capture an image for ``monitor_id``, move the
          camera, capture an image for ``PTZ_MONITOR_ID``, and return the JPEG
          byte array of the two images merged into one, side-by-side.
        """
        if ptz_preset is None:
            return self._get_camera_capture(monitor_id)
        if monitor_id == PTZ_MONITOR_ID:
            self._ptz_to(ptz_preset)
            return self._get_camera_capture(PTZ_MONITOR_ID)
        # else we actually want TWO images...
        # capture the first one, from the non-PTZ camera
        img1 = self._get_camera_capture(monitor_id)
        # move the PTZ camera and capture an image from it
        self._ptz_to(ptz_preset)
        img2 = self._get_camera_capture(PTZ_MONITOR_ID)
        # return the two images combined side-by-side
        return self._combine_images(img1, img2)

    def _get_camera_capture(self, monitor_id):
        """
        Return the JPEG byte array of the current snapshot from the specified
        ZoneMonitor Monitor ID.
        """
        url = 'http://localhost/zm/cgi-bin/nph-zms?' \
              'mode=single&monitor=%s&scale=100' % monitor_id
        self._log.debug('GET %s', url)
        r = requests.get(url)
        r.raise_for_status()
        self._log.debug('Got %d byte response', len(r.content))
        return r.content

    def _combine_images(self, imgA_bytes, imgB_bytes):
        """
        Given two byte arrays containing JPEG images, return the JPEG byte array
        for a single image with the two pasted side-by-side, 10px apart.
        """
        imgA = Image.open(BytesIO(imgA_bytes))
        imgB = Image.open(BytesIO(imgB_bytes))
        widthA, heightA = imgA.size
        widthB, heightB = imgB.size
        total_width = sum([widthA, widthB]) + 10
        max_height = max([heightA, heightB])
        new_im = Image.new('RGB', (total_width, max_height))
        new_im.paste(imgA, (0, 0))
        new_im.paste(imgB, (widthA + 10, 0))
        b = BytesIO()
        new_im.save(b, format='JPEG')
        return b.getvalue()

    def _ptz_to(self, preset_number):
        """
        Move PTZ_CAM_HOST Amcrest camera to the specified PTZ preset number.
        """
        # build the URL to call
        url = 'http://%s/cgi-bin/ptz.cgi?' \
              'action=start&channel=0&code=GotoPreset&arg1=0&' \
              'arg2=%s&arg3=0' % (PTZ_CAM_HOST, preset_number)
        self._log.info('PTZ to %d: %s', preset_number, url)
        da = HTTPDigestAuth(
            self._hass_secrets['amcrest_username'],
            self._hass_secrets['amcrest_password']
        )
        # GET the URL to tell the camera to move
        r = requests.get(url, auth=da)
        # ensure it returned a HTTP 2xx
        r.raise_for_status()
        self._log.debug('PTZ response: %s', r.text)
        # build the URL to confirm PTZ move/status
        conf_url = 'http://%s/cgi-bin/ptz.cgi?action=getStatus' % PTZ_CAM_HOST
        self._log.info('PTZ status check: %s', conf_url)
        # request the confirmation URL. This seems to not return until the
        # movement is complete.
        r = requests.get(url, auth=da)
        # ensure HTTP 2xx
        r.raise_for_status()
        self._log.debug('PTZ response: %s', r.text)

    def _do_notify_pushover(self, title, message, sound=None, image=None):
        """Build Pushover API request arguments and call _send_pushover"""
        d = {
            'data': {
                'token': self._hass_secrets['pushover_api_key'],
                'user': self._hass_secrets['pushover_user_key'],
                'title': title,
                'message': message,
                'url': 'https://redirect.jasonantman.com/hass',
                'retry': 300  # 5 minutes
            },
            'files': {}
        }
        if sound is not None:
            d['data']['sound'] = sound
        if image is None:
            self._log.info('Sending Pushover notification: %s', d)
        else:
            self._log.info('Sending Pushover notification with image: %s', d)
            d['files']['attachment'] = ('frame.jpg', image, 'image/jpeg')
        self._send_pushover(d)

    def _send_pushover(self, params):
        """
        Send the actual Pushover notification.

        We do this directly with ``requests`` because python-pushover still
        doesn't have support for images or some other API options.
        """
        url = 'https://api.pushover.net/1/messages.json'
        self._log.debug('Sending Pushover notification')
        r = requests.post(url, **params)
        self._log.debug(
            'Pushover POST response HTTP %s: %s', r.status_code, r.text
        )
        r.raise_for_status()
        if r.json()['status'] != 1:
            raise RuntimeError('Error response from Pushover: %s', r.text)
        self._log.info('Pushover Notification Success: %s', r.text)
