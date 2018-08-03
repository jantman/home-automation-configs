"""
Door Panel handler app.

Companion to homeassistant/www/doorpanels, providing most of the logic in
response to calls of the "doorpanels" service in the "CUSTOM" domain.

Alarm disarming codes are read from a "alarm_codes" hash in secrets.yaml where
hash keys are alarm codes and values are string descriptions of them.

# Important Notes

- This script retrieves secrets directly from the HASS ``secrets.yaml`` file.
The user it runs as must be able to read that file. The path to the HASS
configuration directory is read from the HASS API in
``_get_hass_secrets()`` via the ``conf_dir`` key of the return
value of ``appdaemon.plugins.hass.hassapi.Hass.get_hass_config()`` and then
``secrets.yaml`` in that file is read and loaded. The expected secrets.yaml
keys are defined in ``_get_hass_secrets()``.

"""

import logging
import os
import appdaemon.plugins.hass.hassapi as hass

from yaml import load as load_yaml
try:
    from yaml import CLoader as Loader, CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper

from sane_app_logging import SaneLoggingApp

#: Entity ID for the input_select that controls the alarm state. This should
#: have three options for the three possible alarm states: Home, Away, and
#: Disarmed. The option strings are defined in the following constants.
ALARM_STATE_SELECT_ENTITY = 'input_select.alarmstate'
HOME = 'Home'
AWAY = 'Away'
DISARMED = 'Disarmed'
AWAY_DELAY = 'Away-Delay'

#: Default for info-as-debug logging via LogWrapper; can be overridden
#: at runtime via events. See ``sane_app_logging.py``.
LOG_DEBUG = False


class DoorPanelHandler(hass.Hass, SaneLoggingApp):
    """
    DoorPanel handler app.
    """

    def initialize(self):
        """
        Initialize the DoorPanelHandler

        Setup logging and some instance variables. Get secrets from HASS
        ``secrets.yaml``. Then find all the entities we care about (sensors,
        device tracker, and the input_select for alarm state) from the HASS API
        and setup listeners for them.
        """
        self._setup_logging(self.__class__.__name__, LOG_DEBUG)
        self._log.info("Initializing DoorPanelHandler...")
        self._hass_secrets = self._get_hass_secrets()
        self.listen_event(
            self._handle_event, event='call_service'
        )
        self._leave_timer = None

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
        assert 'alarm_codes' in conf
        # return the full dict
        return conf

    @property
    def alarm_state(self):
        """Return the string state of the alarm_state input select."""
        return self.get_state(ALARM_STATE_SELECT_ENTITY)

    def _handle_event(self, event_name, data, _):
        if data.get('domain', '') != 'custom':
            return
        if data.get('service', '') != 'doorpanels':
            return
        self._log.debug('Got service call: %s', data['service_data'])
        client = data['service_data'].get('client', 'unknown')
        if data['service_data']['type'] == 'leave':
            return self._handle_leave(client)
        if data['service_data']['type'] == 'stay':
            return self._handle_stay(client)
        if data['service_data']['type'] == 'disarm':
            return self._handle_disarm(client)
        if data['service_data']['type'] == 'enterCode':
            return self._handle_code(data['service_data']['code'], client)

    def _handle_leave(self, client_ip):
        self._log.info(
            'Requesting AWAY_DELAY from client %s', client_ip
        )
        self.fire_event(
            'CUSTOM_ALARM_STATE_SET', state=AWAY_DELAY
        )

    def _handle_stay(self, client_ip):
        self._log.info('Handle "stay" from %s', client_ip)
        if self.alarm_state == HOME:
            self._log.info(
                'Ignoring stay/Home request from %s when already Home',
                client_ip
            )
            return
        if self._leave_timer is not None:
            self.cancel_timer(self._leave_timer)
            self._leave_timer = None
        self._log.info(
            'Alarm armed Home from %s', client_ip
        )
        self.call_service(
            'logbook/log', name='Alarm armed Home/stay',
            message='From %s' % client_ip
        )
        self.fire_event(
            'CUSTOM_ALARM_STATE_SET', state=HOME
        )

    def _handle_disarm(self, client_ip):
        if self.alarm_state == AWAY:
            self.fire_event(
                'CUSTOM_ALARM_TRIGGER',
                message='Doorpanel disarm attempt when armed Away '
                        'from %s' % client_ip
            )
            self._log.warning(
                'Alarm disarm attempt when Away from %s' % client_ip
            )
            return
        if self.alarm_state == DISARMED:
            self._log.info(
                'Ignoring Disarm request from %s when already disarmed',
                client_ip
            )
            return
        self._log.info(
            'Alarm disarmed from %s', client_ip
        )
        self.call_service(
            'logbook/log', name='Alarm Disarmed via Doorpanel',
            message='From %s' % client_ip
        )
        self.fire_event(
            'CUSTOM_ALARM_STATE_SET', state=DISARMED
        )

    def _handle_code(self, code, client_ip):
        self._log.info('Handle code "%s" from %s', code, client_ip)
        if self.alarm_state == DISARMED:
            self._log.info(
                'Ignoring Disarm request with code from %s when already '
                'disarmed', client_ip
            )
            return
        desc = self._hass_secrets['alarm_codes'].get(code, None)
        if desc is None:
            self.fire_event(
                'CUSTOM_ALARM_TRIGGER',
                message='Doorpanel disarm attempt with invalid '
                        'code %s from %s' % (code, client_ip)
            )
            self._log.warning(
                'Alarm disarm attempt with invalid code from %s' % client_ip
            )
            return
        self._log.info(
            'Alarm disarmed with code: %s from %s', desc, client_ip
        )
        self.call_service(
            'logbook/log', name='Alarm Disarmed via Doorpanel',
            message='Code used: %s from %s' % (desc, client_ip)
        )
        self.fire_event(
            'CUSTOM_ALARM_STATE_SET', state=DISARMED
        )
