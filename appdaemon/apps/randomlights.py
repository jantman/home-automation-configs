"""
Random Lights App

Randomly changes lights to make house appear occupied. Currently runs 24x7.

Uses a hard-coded list of entities to control.
"""

from random import randint, sample
import appdaemon.plugins.hass.hassapi as hass
import datetime

from sane_app_logging import SaneLoggingApp

#: Entity ID for the input_select that controls the alarm state. This should
#: have three options for the three possible alarm states: Home, Away, and
#: Disarmed. The option strings are defined in the following constants.
CONTROL_INPUT_ENTITY = 'input_boolean.enable_randomlights'

#: Default for info-as-debug logging via LogWrapper; can be overridden
#: at runtime via events. See ``sane_app_logging.py``.
LOG_DEBUG = False

#: List of entities to select from
LIGHT_ENTITIES = [
    'group.kitchenlights',
    'group.porchlights',
    'switch.workbenchlight_switch',
    'group.brbulbs',
    'group.officebulbs',
    'group.lrbulbs',
    'light.backroomlightlevel_on_off',
    'switch.backroomshoplights_on_off',
]


class RandomLights(hass.Hass, SaneLoggingApp):
    """
    Random lights app.
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
        self._log.info("Initializing RandomLights...")
        self._timer = None
        self.set_timer()
        self._log.info('Done initializing RandomLights.')

    def set_timer(self):
        """
        Clear the hourly timer if it exists. Set the hourly timer (self._timer)
        to a random minute of the hour.
        """
        if self._timer is not None:
            self._log.debug('Canceling existing timer')
            self.cancel_timer(self._timer)
        newtime = self.datetime() + datetime.timedelta(
            minutes=randint(45, 75)
        )
        self._log.info('Next iteration will be at: %s', newtime)
        self.call_service(
            'logbook/log', name='RandomLights',
            message='Next run at: %s' % newtime
        )
        self._timer = self.run_at(self.timer_callback, newtime)

    def timer_callback(self, _):
        self._log.info('Timer callback fired.')
        self.set_timer()
        # check input_boolean
        if self.get_state(CONTROL_INPUT_ENTITY) == 'off':
            self._log.info(
                'Skipping RandomLights - %s is off', CONTROL_INPUT_ENTITY
            )
            return
        # figure out which lights to turn on
        on_lights = sample(LIGHT_ENTITIES, randint(1, len(LIGHT_ENTITIES)))
        self._log.info('Lights to turn on: %s', on_lights)
        self.call_service(
            'logbook/log', name='RandomLights',
            message='Lights to turn ON: %s' % on_lights
        )
        delay = 0
        for ename in LIGHT_ENTITIES:
            delay += randint(0, 30)
            if ename in on_lights:
                action = True
                self._log.info('Turn %s on in %ss', ename, delay)
            else:
                action = False
                self._log.info('Turn %s off in %ss', ename, delay)
            self.run_in(
                self.light_callback, delay,
                turn_on=action, entity_id=ename
            )

    def light_callback(self, kwargs):
        eid = kwargs['entity_id']
        if kwargs['turn_on']:
            self._log.info('Turning ON: %s', eid)
            self.turn_on(eid)
        else:
            self._log.info('Turning OFF: %s', eid)
            self.turn_off(eid)
