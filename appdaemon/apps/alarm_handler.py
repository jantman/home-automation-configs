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
value of ``appdaemon.plugins.hass.hassapi.Hass.get_plugin_config()`` and
then ``secrets.yaml`` in that file is read and loaded. The expected secrets.yaml
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
- Turn on/off a list of ZoneMinder cameras when system is armed in Away.
- Alarm state set based on manual input_select in UI or device tracker. If the
  device_tracker entity_id for my phone (configurable) enters the "Home" zone,
  disarm the alarm. If it leaves the "Home" zone, arm it as Away.
- Listens for an event, ``CUSTOM_ALARM_STATE_SET``, to set the state. Event data
  is a ``state`` key with possible values the same as the input_select options.
- Listens for a ``CUSTOM_ALARM_TRIGGER`` event. If found, triggers the alarm
  with a message from the ``message`` event data key.
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
import time
import os
import requests
from requests.auth import HTTPDigestAuth
from PIL import Image
from io import BytesIO
from random import randint
from base64 import b64decode, b64encode
import appdaemon.plugins.hass.hassapi as hass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from pathlib import Path

from sane_app_logging import SaneLoggingApp
from pushover_notifier import PushoverNotifier

#: List of regular expressions to match the binary_sensor entities for my
#: "exterior" zone, i.e. things that alarm when I'm either Home or Away
EXTERIOR_SENSOR_REs = [
    re.compile(r'^binary_sensor\.ecolink_doorwindow_sensor_sensor.*$'),
    re.compile(r'^binary_sensor\.gate_sensor$'),
    re.compile(r'^binary_sensor\.crawlspace_sensor$'),
]

#: List of regular expressions to match the binary_sensor entities for my
#: "interor" zone, i.e. things that alarm only when I'm Away.
INTERIOR_SENSOR_REs = [
    re.compile(r'^binary_sensor\.ecolink_motion_detector_sensor.*$'),
    re.compile(r'^binary_sensor\..*_motion$'),
]

#: List of regular expressions to match the binary_sensor entities for any
#: sensors that should not alarm for ``DELAYED_EXTERIOR_SENSOR_DELAY_SEC``
#: seconds after arming the alarm, and should not fail arming the alarm if
#: they are open/triggered when arming is requested.
DELAYED_EXTERIOR_SENSOR_REs = []

#: Integer number of seconds for how long to delay triggering off of
#: ``DELAYED_EXTERIOR_SENSOR_REs`` after arming the alarm.
DELAYED_EXTERIOR_SENSOR_DELAY_SEC = 360 # 6 minutes

#: Device tracker entity ID for my phone, for arming/disarming based on
#: presence or proximity.
DEVICE_TRACKER_ENTITY = 'device_tracker.555924e18d8ed3d2'

#: Entity ID for the input_select that controls the alarm state. This should
#: have three options for the three possible alarm states: Home, Away, and
#: Disarmed. The option strings are defined in the following constants.
ALARM_STATE_SELECT_ENTITY = 'input_select.alarmstate'
HOME = 'Home'
AWAY = 'Away'
DISARMED = 'Disarmed'
AWAY_DELAY = 'Away-Delay'
DISARMED_DURESS = 'Disarmed-Duress'
DURESS = 'Duress'
END_DURESS = 'End-Duress'

#: Entity ID for the input_boolean for alarm duress mode.
ALARM_DURESS_ENTITY = 'input_boolean.alarm_duress'

#: Entity ID for input_boolean that enables alarming on interior sensors
INTERIOR_ENABLE_ENTITY = 'input_boolean.enable_motion'

#: List of entity IDs that should be turned on for 10 minutes after an alarm.
LIGHT_ENTITIES = [
    # Kitchen
    'light.kitchenbulb1level_on_off',
    'light.kitchenbulb2level_on_off',
    # Porch
    'light.cree_connected_a_19_60w_equivalent_fe0b0886_10',
    'light.cree_connected_a_19_60w_equivalent_fe0afc46_10',
    # TV
    'switch.workbenchlight_switch',
    # Living Room
    'light.jasco_products_45606_2_way_dimmer_switch_level',
    # Bedroom
    'light.ge_45606_2way_dimmer_switch_level',
    # Office
    'light.ge_45606_2way_dimmer_switch_level_2',
    # Deck string lights
    'switch.inovelli_unknown_type_ff00_id_ff07_switch',
    # back room light
    'light.backroomlightlevel_on_off',
    # back room shop lights
    'switch.backroomshoplights_on_off',
]

#: List of RGB light entities that should react to an alarm. Right now they
#: act the same way as LIGHT_ENTITIES, but at some point I may make them flash
#: colors.
RGB_LIGHT_ENTITIES = []

#: If an alarm is triggered based on state change of one of these entity IDs,
#: a snapshot from the specified ZoneMinder Monitor ID will be attached.
#: The second argument specifies a PTZ ID to move PTZ_MONITOR_ID to before
#: snapshotting it. If the Monitor ID is not PTZ_MONITOR_ID, a snapshot of
#: both the first element (Monitor ID) and PTZ_MONITOR_ID panned to the PTZ
#: preset will be included, side by side in one image.
CAMERA_IMAGE_ENTITIES = {
    'binary_sensor.kitchen_motion': {'monitor_id': 2, 'ptz_preset': 2},
    'binary_sensor.livingroom_motion': {'monitor_id': 2, 'ptz_preset': 1},
    # crawlspace
    'binary_sensor.crawlspace_sensor': {'monitor_id': 5},
    # gate
    'binary_sensor.gate_sensor': {'monitor_id': 5},
    # kitchen
    'binary_sensor.ecolink_doorwindow_sensor_sensor_4': {
        'monitor_id': 2, 'ptz_preset': 2, 'second_monitor_id': 4
    },
    # front door
    'binary_sensor.ecolink_doorwindow_sensor_sensor': {
        'monitor_id': 2, 'ptz_preset': 1, 'second_monitor_id': 3
    },
    # back room
    'binary_sensor.ecolink_motion_detector_sensor': {
        'monitor_id': 8, 'ptz_preset': 3
    },
    # office
    'binary_sensor.office_motion': {'monitor_id': 6},
    # bedroom
    'binary_sensor.bedroom_motion': {'monitor_id': 7}
}

#: Dict of alarm entities to camera entity to show
HASS_CAMERA_ENTITIES = {
    'binary_sensor.kitchen_motion': 'camera.lrkitchen',
    'binary_sensor.livingroom_motion': 'camera.lrkitchen',
    # crawlspace
    'binary_sensor.crawlspace_sensor': 'camera.side',
    # gate
    'binary_sensor.gate_sensor': 'camera.side',
    # kitchen
    'binary_sensor.ecolink_doorwindow_sensor_sensor_4': 'camera.back',
    # front door
    'binary_sensor.ecolink_doorwindow_sensor_sensor': 'camera.porch',
    # back room
    'binary_sensor.ecolink_motion_detector_sensor': 'camera.hall',
    # office
    'binary_sensor.office_motion': 'camera.office',
    # bedroom
    'binary_sensor.bedroom_motion': 'camera.bedrm'
}

#: List of camera entities to turn on when system is armed in AWAY mode, and
#: turn off when camera is in HOME or DISARMED.
AWAY_CAMERA_ENTITIES = [
    'switch.bedrm_state',
    'switch.hall_state',
    'switch.lrkitchen_state',
    'switch.office_state'
]

#: Dictionary of monitor_id to hostname/IP for Amcrest PTZ cameras.
PTZ_CAM_HOSTS = {
    2: '192.168.99.110',
    8: '192.168.99.160'
}

#: Default for info-as-debug logging via LogWrapper; can be overridden
#: at runtime via events. See ``sane_app_logging.py``.
LOG_DEBUG = False

#: Delay from requesting delayed away arming, until armed
AWAY_SECONDS = 15

#: If armed AWAY and input_boolean.no_alarm_delay is "off", how many seconds to
#: wait for disarming before triggering the alarm.
AWAY_TRIGGER_DELAY_SECONDS = 10

#: List of entity IDs which, when triggered in AWAY with
#: input_boolean.no_alarm_delay is "off", will cause a delayed trigger of the
#: alarm. Entities not in this list will not delay (i.e. alarm will trigger
#: immediately).
AWAY_DELAY_ENTITIES = [
    # front door
    'binary_sensor.ecolink_doorwindow_sensor_sensor',
    'binary_sensor.livingroom_motion',
]

#: Path of a file to "touch" whenever the alarm changes state.
TRANSITION_FILE_PATH = '/tmp/alarm_last_state_transition'

#: Number of seconds to timeout for requests to ZM API
ZM_API_TIMEOUT = 5

#: Number of seconds to timeout for PTZ requests to cameras
PTZ_TIMEOUT = 2


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


class AlarmHandler(hass.Hass, SaneLoggingApp, PushoverNotifier):
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
        self.listen_event(
            self._handle_trigger_event, event='CUSTOM_ALARM_TRIGGER'
        )
        self._leave_timer = None
        self._trigger_delay_timer = None
        self._untrigger_timer = None
        # get the current state time
        try:
            self._last_transition_time = os.stat(TRANSITION_FILE_PATH).st_mtime
        except Exception:
            self._log.error(
                'Unable to read transition file mtime: %s',
                TRANSITION_FILE_PATH, exc_info=True
            )
            self._last_transition_time = 0
        # end get current state time
        self._log.info('Done initializing AlarmHandler')

    @property
    def alarm_state(self):
        """Return the string state of the alarm_state input select."""
        return self.get_state(ALARM_STATE_SELECT_ENTITY)

    @property
    def in_duress(self):
        """Return True if in DURESS mode, False otherwise."""
        return self.get_state(ALARM_DURESS_ENTITY) == 'on'

    def _update_alarm_state_file(self, state):
        self._last_transition_time = time.time()
        try:
            with open(TRANSITION_FILE_PATH, 'w') as fh:
                fh.write(state)
        except Exception:
            self._log.error(
                'Error writing alarm state to state file', exc_info=True
            )

    @property
    def _in_delayed_exterior_period(self):
        cutoff = self._last_transition_time + DELAYED_EXTERIOR_SENSOR_DELAY_SEC
        if time.time() < cutoff:
            self._log.debug('Currently in delayed exterior period')
            return True
        return False

    def _is_delayed_exteriod_entity(self, entity):
        for e_re in DELAYED_EXTERIOR_SENSOR_REs:
            if e_re.match(entity):
                return True
        return False

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

    def _is_entity_silenced(self, entity_id, friendly_name=None):
        if friendly_name is None:
            friendly_name = self.get_state(entity_id, 'friendly_name')
            self._log.info(
                'Set friendly_name for %s to %s', entity_id, friendly_name
            )
        ib_name = 'input_boolean.silence_' + friendly_name.lower().replace(
            ' ', '_'
        )
        ib_state = self.get_state(ib_name)
        if ib_state is None:
            ib_state = False
        else:
            ib_state = ib_state != 'off'
        self._log.info('State of %s is %s', ib_name, ib_state)
        return ib_state

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
        if self.get_state(INTERIOR_ENABLE_ENTITY) == 'off':
            self._log.info(
                '%s is off; Ignoring interior state change '
                '(%s %s from %s to %s)', INTERIOR_ENABLE_ENTITY,
                fmt_entity(entity, kwargs), attribute, old, new
            )
            return
        if self._is_entity_silenced(
            entity, friendly_name=kwargs.get('friendly_name', None)
        ):
            self._log.info(
                'Ignoring state change %s %s from %s to %s - entity silenced',
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
        # If we have a camera pointing (or point-able via PTZ) at this sensor,
        # get the image from it to include in our notification.
        image = None
        if entity in CAMERA_IMAGE_ENTITIES.keys():
            image = self._image_for_camera(**CAMERA_IMAGE_ENTITIES[entity])

        self._trigger_alarm(
            subject='ALARM %s TRIGGERED: %s %s' % (a_state, e_name, st_name),
            message='System is in state %s; %s %s changed from %s to %s'
            ' (Interior Zone)' % (
                a_state, fmt_entity(entity, kwargs), attribute, old, new
            ),
            image=image, entity=entity,
            hass_camera_entity=HASS_CAMERA_ENTITIES.get(entity)
        )

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
        if (
            self._in_delayed_exterior_period and
            self._is_delayed_exteriod_entity(entity)
        ):
            self._log.warning(
                'In DELAYED_EXTERIOR_SENSOR_DELAY_SEC; disregarding exterior '
                'state change (%s %s from %s to %s).',
                fmt_entity(entity, kwargs), attribute, old, new
            )
            return
        if self._is_entity_silenced(
            entity, friendly_name=kwargs.get('friendly_name', None)
        ):
            self._log.info(
                'Ignoring state change %s %s from %s to %s - entity silenced',
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
        # If we have a camera pointing (or point-able via PTZ) at this sensor,
        # get the image from it to include in our notification.
        image = None
        if entity in CAMERA_IMAGE_ENTITIES.keys():
            image = self._image_for_camera(**CAMERA_IMAGE_ENTITIES[entity])
        self._trigger_alarm(
            subject='ALARM %s TRIGGERED: %s %s' % (a_state, e_name, st_name),
            message='System is in state %s; %s %s changed from %s to %s'
            ' (Exterior Zone)' % (
                a_state, fmt_entity(entity, kwargs), attribute, old, new
            ),
            image=image, entity=entity,
            hass_camera_entity=HASS_CAMERA_ENTITIES.get(entity)
        )

    def _handle_trigger_event(self, event_name, data, _):
        """
        Handle the CUSTOM_ALARM_TRIGGER event.

        event type: CUSTOM_ALARM_TRIGGER
        data: dict with one key, ``message``.
        """
        self._log.info('Got %s event data=%s', event_name, data)
        msg = data.get('message', '<no message>')
        self._trigger_alarm(
            subject='ALARM TRIGGERED by Event',
            message='Event Message: %s' % msg
        )

    def _handle_state_set_event(self, event_name, data, _):
        """
        Handle the CUSTOM_ALARM_STATE_SET event.

        event type: LOGWRAPPER_SET_DEBUG
        data: dict with one key, ``state``. String value must match the value
        of one of :py:const:`~.HOME`, :py:const:`~.AWAY`,
        :py:const:`~.DISARMED`, :py:const:`~.DISARMED_DURESS`,
        :py:const:`~.DURESS`, or :py:const:`~.END_DURESS`.
        """
        self._log.debug('Got %s event data=%s', event_name, data)
        if event_name != 'CUSTOM_ALARM_STATE_SET':
            self._log.error(
                'Got event of improper type: %s', event_name
            )
            return
        self._log.info('Handle state set event: %s', data)
        state = data.get('state', None)
        prev_state = self.get_state(ALARM_STATE_SELECT_ENTITY)
        if state not in [
            HOME, AWAY, DISARMED, AWAY_DELAY, DURESS, END_DURESS,
            DISARMED_DURESS
        ]:
            self._log.error(
                'Got invalid state for CUSTOM_ALARM_STATE_SET event: %s',
                state
            )
            return
        if state == prev_state:
            self._log.info(
                'Got CUSTOM_ALARM_STATE_SET event with state=%s but alarm is '
                'already in that state. Ignoring.', state
            )
            return
        if state in [DURESS, END_DURESS]:
            self._log.info('Got %s event', state)
            self._handle_duress(state)
            return
        if state == DISARMED_DURESS:
            self._log.info('Got Disarm-Duress event')
            self._disarm(prev_state, is_duress=True)
            return
        if state == HOME:
            self._log.info('Arming HOME from event')
            self._arm_home(prev_state)
            return
        if state == AWAY:
            self._log.info('Arming AWAY from event')
            self._arm_away(prev_state)
            return
        if state == AWAY_DELAY:
            self._log.info('Handle AWAY_DELAY event')
            self._arm_away_delay(prev_state)
            return
        self._log.info('Disarming from event')
        self._disarm(prev_state)

    def _handle_duress(self, new_state):
        if new_state == DURESS:
            self._log.info('Handling DURESS event')
            self._log.info('Turning on cameras: %s', AWAY_CAMERA_ENTITIES)
            Path('/tmp/camera_control.time').touch()
            for cam_entity in AWAY_CAMERA_ENTITIES:
                self.turn_on(cam_entity)
            self.turn_on(ALARM_DURESS_ENTITY)
            return
        # else END_DURESS
        self._log.info('Handling END_DURESS event')
        self._log.info('Turning off cameras: %s', AWAY_CAMERA_ENTITIES)
        Path('/tmp/camera_control.time').touch()
        for cam_entity in AWAY_CAMERA_ENTITIES:
            self.turn_off(cam_entity)
        self.turn_off(ALARM_DURESS_ENTITY)

    def _arm_away_delay(self, prev_state):
        self._log.info(
            'Begin delayed AWAY arming (previous state: %s; '
            'delay of %d seconds)', prev_state, AWAY_SECONDS
        )
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
            return
        self._update_alarm_state_file('AWAY_DELAY')
        self.turn_on('input_boolean.arming_away')
        self._leave_timer = self.run_in(
            self._arm_away_delay_callback, AWAY_SECONDS, prev_state=prev_state
        )

    def _arm_away_delay_callback(self, kwargs):
        self._arm_away(kwargs['prev_state'])

    def _trigger_alarm(
        self, subject='Alarm Triggered', message='alarm triggered', image=None,
        entity=None, hass_camera_entity=None
    ):
        """Trigger the alarm"""
        self._log.debug(
            'Called _trigger_alarm; subject="%s" message="%s" %s',
            subject, message, 'with image' if image is not None else 'no image'
        )
        if (
            self.alarm_state == AWAY and
            self.get_state('input_boolean.no_alarm_delay') == 'off' and
            self._trigger_delay_timer is None and
            entity in AWAY_DELAY_ENTITIES
        ):
            self._log.debug(
                'Delaying alarm trigger by %ss', AWAY_TRIGGER_DELAY_SECONDS
            )
            self.turn_on('input_boolean.trigger_delay')
            trigger_args = {
                'subject': subject, 'message': message, 'image': image,
                'entity': entity
            }
            if image is not None:
                trigger_args['image'] = b64encode(image)
            self._trigger_delay_timer = self.run_in(
                self._trigger_alarm_delay_callback, AWAY_TRIGGER_DELAY_SECONDS,
                **trigger_args
            )
            return
        # remove any trigger delay
        if self._trigger_delay_timer is not None:
            self.cancel_timer(self._trigger_delay_timer)
            self._trigger_delay_timer = None
        # Add event/trigger to logbook
        self.call_service(
            'logbook/log', name=subject, message=message
        )
        self._browsermod_show_camera(hass_camera_entity)
        self._do_notify_pushover(
            subject, message, image=image, sound='alien'
        )
        self._do_alarm_lights()
        self._notify_email(subject, message, image=image)
        # revert the lights somewhere from 10 to 20 minutes later
        undo_delay = randint(600, 1200)
        self._log.info(
            'Scheduling _untrigger_alarm in %d seconds', undo_delay
        )
        self.turn_off('input_boolean.trigger_delay')
        self._untrigger_timer = self.run_in(self._untrigger_alarm, undo_delay)

    def _trigger_alarm_delay_callback(self, kwargs):
        img = kwargs['image']
        if img is not None:
            img = b64decode(img)
        self._trigger_alarm(
            subject=kwargs['subject'], message=kwargs['message'],
            image=img, entity=kwargs['entity']
        )

    def _untrigger_alarm(self, _):
        """Un-trigger / reset the alarm"""
        self._undo_alarm_lights(None)
        if self._untrigger_timer is not None:
            self.cancel_timer(self._untrigger_timer)
        self._untrigger_timer = None

    def _do_alarm_lights(self):
        """
        Turn on all lights when alarm goes off. Save state of all lights before
        turning on, and revert them 10-20 minutes later.
        """
        self._log.info('Turning on all lights')
        for e_id in LIGHT_ENTITIES + RGB_LIGHT_ENTITIES:
            self._light_states[e_id] = self.get_state(e_id)
            self.turn_on(e_id)
        self._log.info(
            'All lights turned on. Previous state: %s', self._light_states
        )

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

    def _reset_input_booleans(self):
        # turn off the camera-silencing inputs when alarm state changes
        for e in self.get_state('input_boolean').values():
            if e is None:
                continue
            eid = e['entity_id']
            if not (
                eid.startswith('input_boolean.silence_') or
                eid == 'input_boolean.cameras_silent' or
                eid.startswith('input_boolean.enable_') or
                eid == 'input_boolean.no_alarm_delay' or
                eid == 'input_boolean.arming_away' or
                eid == 'input_boolean.trigger_delay'
            ):
                self._log.info('Not resetting input_boolean: %s', eid)
                continue
            a = e.get('attributes', {})
            self._log.info('Turning OFF: %s (%s)', eid, a['friendly_name'])
            self.turn_off(eid)
        self.turn_on('input_boolean.bedpi_display_wake')
        self.turn_on('input_boolean.couchpi_display_wake')

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
        self._update_alarm_state_file('HOME')
        self._do_notify_pushover(
            'System Armed - Home',
            'System has been armed in "Home" mode. All exterior sensors '
            'secure.', sound='gamelan'
        )
        if self.in_duress:
            self._log.info('In DURESS mode; not turning off cameras.')
        else:
            self._log.info('Turning off cameras: %s', AWAY_CAMERA_ENTITIES)
            Path('/tmp/camera_control.time').touch()
            for cam_entity in AWAY_CAMERA_ENTITIES:
                self.turn_off(cam_entity)
        self._reset_input_booleans()
        self.select_option(ALARM_STATE_SELECT_ENTITY, HOME)

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
        self._update_alarm_state_file('AWAY')
        self._do_notify_pushover(
            'System Armed - Away',
            'System has been armed in "Away" mode. All exterior sensors '
            'secure.', sound='gamelan'
        )
        self._log.info('Turning on cameras: %s', AWAY_CAMERA_ENTITIES)
        Path('/tmp/camera_control.time').touch()
        for cam_entity in AWAY_CAMERA_ENTITIES:
            self.turn_on(cam_entity)
        self._reset_input_booleans()
        self.select_option(ALARM_STATE_SELECT_ENTITY, AWAY)
        self.turn_off('input_boolean.arming_away')

    def _disarm(self, prev_state, is_duress=False):
        """Disarm the system."""
        self._log.info('Disarming system (previous state: %s)', prev_state)
        self._update_alarm_state_file('DISARMED')
        # remove any trigger delay
        if self._trigger_delay_timer is not None:
            self.cancel_timer(self._trigger_delay_timer)
            self._trigger_delay_timer = None
        # cancel any current alarm
        if self._untrigger_timer is not None:
            self._untrigger_alarm(None)
        self.turn_off('input_boolean.trigger_delay')
        self._do_notify_pushover(
            'System Disarmed',
            'System has been disarmed.'
        )
        if not is_duress and not self.in_duress:
            self._log.info('Turning off cameras: %s', AWAY_CAMERA_ENTITIES)
            Path('/tmp/camera_control.time').touch()
            for cam_entity in AWAY_CAMERA_ENTITIES:
                self.turn_off(cam_entity)
        else:
            self._log.info('Disarmed DURESS mode; not turning off cameras.')
            self.turn_on(ALARM_DURESS_ENTITY)
        self._reset_input_booleans()
        self.select_option(ALARM_STATE_SELECT_ENTITY, DISARMED)

    def _exterior_doors_open(self):
        """Return a list of the friendly_name of any open exterior sensors."""
        opened = []
        for eid, friendly_name in self._exterior_sensors.items():
            if self.get_state(eid) != 'on':
                continue
            if self._is_delayed_exteriod_entity(eid):
                self._log.warning(
                    'Entity %s (%s) is in open state but listed in '
                    'DELAYED_EXTERIOR_SENSOR_REs; ignoring open state',
                    eid, friendly_name
                )
            else:
                opened.append(friendly_name)
        return opened

    def _image_for_camera(
        self, monitor_id=None, ptz_preset=None, second_monitor_id=None
    ):
        """
        Retrieve an image for the specified camera(s).

        - If ``second_monitor_id`` is not None, it is a non-PTZ monitor.
          Snapshot that monitor, than move ``monitor_id`` to ``ptz_preset`` and
          snapshot it, and return the combined image from both.
        - If ``ptz_preset`` is not specified, return the return value of
          :py:meth:`~._get_camera_capture` for ``monitor_id``.
        - If ``ptz_preset`` is specified and ``monitor_id`` is
          a key in ``PTZ_CAM_HOSTS``, call :py:meth:`~._ptz_to` to move the
          camera and then return the return value of
          :py:meth:`~._get_camera_capture` for ``monitor_id``.
        """
        # Trigger manual alarms on monitors for 30s, after a short delay
        try:
            self._trigger_zm_alarm({'monitor_id': monitor_id})
        except Exception:
            self._log.critical(
                'Error triggering ZM alarm on monitor %s', monitor_id,
                exc_info=True
            )
        self.run_in(self._untrigger_zm_alarm, 30, monitor_id=monitor_id)
        if second_monitor_id is not None:
            try:
                self._trigger_zm_alarm({'monitor_id': second_monitor_id})
            except Exception:
                self._log.critical(
                    'Error triggering ZM alarm on monitor %s',
                    second_monitor_id, exc_info=True
                )
            self.run_in(
                self._untrigger_zm_alarm, 30, monitor_id=second_monitor_id
            )
        if second_monitor_id is not None:
            # capture the first one, from the non-PTZ camera
            try:
                img1 = self._get_camera_capture(second_monitor_id)
            except Exception:
                img1 = None
                self._log.critical(
                    'Error getting camera capture for second_monitor_id %s ',
                    second_monitor_id, exc_info=True
                )
            try:
                # move the PTZ camera and capture an image from it
                self._ptz_to(monitor_id, ptz_preset)
            except Exception:
                self._log.critical(
                    'Error setting monitor %s to ptz_preset=%s',
                    monitor_id, ptz_preset, exc_info=True
                )
            try:
                img2 = self._get_camera_capture(monitor_id)
            except Exception:
                self._log.critical(
                    'Error getting camera capture for monitor %s ',
                    monitor_id, ptz_preset, exc_info=True
                )
                img2 = None
            if img1 is None and img2 is not None:
                return img2
            elif img2 is None and img1 is not None:
                return img1
            elif img2 is None and img1 is None:
                return None
            # return the two images combined side-by-side
            return self._combine_images(img1, img2)
        if ptz_preset is not None:
            try:
                self._ptz_to(monitor_id, ptz_preset)
            except Exception:
                self._log.critical(
                    'Error setting monitor %s to ptz_preset=%s',
                    monitor_id, ptz_preset, exc_info=True
                )
        try:
            return self._get_camera_capture(monitor_id)
        except Exception:
            self._log.critical(
                'Error getting capture for monitor_id=%s',
                monitor_id, exc_info=True
            )
            return None

    def _trigger_zm_alarm(self, kwargs):
        """
        Trigger a manual alarm on a ZM monitor.
        """
        monitor_id = kwargs['monitor_id']
        self._log.info('Trigger ZM alarm on monitor: %s', monitor_id)
        self._log.info('Triggering ZM alarms is disabled')
        return
        url = 'http://172.19.0.1/zm/api/monitors/alarm' \
              '/id:%s/command:on.json' % monitor_id
        self._log.debug('GET %s', url)
        r = requests.get(url, timeout=ZM_API_TIMEOUT)
        self._log.debug('Got HTTP %d: %s', r.status_code, r.text)

    def _untrigger_zm_alarm(self, kwargs):
        """
        Untrigger a manual alarm on a ZM monitor.
        """
        monitor_id = kwargs['monitor_id']
        self._log.info('Untrigger ZM alarm on monitor: %s', monitor_id)
        self._log.info('Triggering ZM alarms is disabled')
        return
        url = 'http://172.19.0.1/zm/api/monitors/alarm' \
              '/id:%s/command:off.json' % monitor_id
        self._log.debug('GET %s', url)
        r = requests.get(url, timeout=ZM_API_TIMEOUT)
        self._log.debug('Got HTTP %d: %s', r.status_code, r.text)

    def _get_camera_capture(self, monitor_id):
        """
        Return the JPEG byte array of the current snapshot from the specified
        ZoneMonitor Monitor ID.
        """
        url = 'http://172.19.0.1/zm/cgi-bin/nph-zms?' \
              'mode=single&monitor=%s&scale=100' % monitor_id
        self._log.debug('GET %s', url)
        r = requests.get(url, timeout=ZM_API_TIMEOUT)
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

    def _ptz_to(self, monitor_id, preset_number):
        """
        Move PTZ_CAM_HOST[monitor_id] Amcrest camera to the specified PTZ
        preset number.
        """
        # build the URL to call
        cam_host = PTZ_CAM_HOSTS.get(monitor_id, None)
        if cam_host is None:
            self._log.warning(
                'PTZ_CAM_HOSTS has no entry for monitor_id=%s', monitor_id
            )
            return
        url = 'http://%s/cgi-bin/ptz.cgi?' \
              'action=start&channel=0&code=GotoPreset&arg1=0&' \
              'arg2=%s&arg3=0' % (cam_host, preset_number)
        self._log.info('PTZ to %d: %s', preset_number, url)
        da = HTTPDigestAuth(
            self._hass_secrets['amcrest_username'],
            self._hass_secrets['amcrest_password']
        )
        # GET the URL to tell the camera to move
        r = requests.get(url, auth=da, timeout=PTZ_TIMEOUT)
        # ensure it returned a HTTP 2xx
        r.raise_for_status()
        self._log.debug('PTZ response: %s', r.text)
        # build the URL to confirm PTZ move/status
        conf_url = 'http://%s/cgi-bin/ptz.cgi?action=getStatus' % cam_host
        self._log.info('PTZ status check: %s', conf_url)
        # request the confirmation URL. This seems to not return until the
        # movement is complete.
        r = requests.get(url, auth=da, timeout=PTZ_TIMEOUT)
        # ensure HTTP 2xx
        r.raise_for_status()
        self._log.debug('PTZ response: %s', r.text)

    def _notify_email(self, subject, message, image=None):
        """
        Build the email message; return a string email message.
        """
        msg = MIMEMultipart()
        msg['Subject'] = subject
        msg['From'] = self._hass_secrets['gmail_username']
        msg['To'] = self._hass_secrets['gmail_username']
        html = '<html><head></head><body>\n'
        html += '<p>Alarm has been triggered:</p>\n'
        html += '<p>%s</p>\n' % message
        html += '</body></html>\n'
        msg.attach(MIMEText(html, 'html'))
        if image is not None:
            msg.attach(
                MIMEImage(image, name='frame.jpg')
            )
        self._do_notify_email(msg.as_string())

    def _turn_off_callback(self, kwargs):
        try:
            self.turn_off(kwargs['entity_id'])
        except Exception as ex:
            self._log.error(
                'Exception turning off %s: %s', kwargs['entity_id'], ex
            )
            raise

    def _call_service_callback(self, kwargs):
        try:
            self.call_service(kwargs['service'], **kwargs['service_kwargs'])
        except Exception as ex:
            self._log.error(
                'Exception calling service: %s %s: %s',
                kwargs['service'], kwargs['service_kwargs'], ex
            )
            raise

    def _browsermod_show_camera(self, camera_entity):
        if camera_entity is None:
            return
        self.run_in(
            self._turn_off_callback, 1, entity_id='switch.couchpi_display'
        )
        self.run_in(
            self._turn_off_callback, 1, entity_id='switch.bedpi_display'
        )
        self.run_in(
            self._call_service_callback, 1, service='browser_mod/more_info',
            service_kwargs={'entity_id': camera_entity}
        )
