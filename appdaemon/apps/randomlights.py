"""
Random Lights App

Randomly changes lights starting an hour before sunset and ending an hour after
sunrise, to make house appear occupied.

Uses a hard-coded list of entities to control.
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
CONTROL_INPUT_ENTITY = 'input_boolean.enable_randomlights'

#: Default for info-as-debug logging via LogWrapper; can be overridden
#: at runtime via events. See ``sane_app_logging.py``.
LOG_DEBUG = False

#: List of entities to select from
LIGHT_ENTITIES = [
    'group.kitchenlights',
    'group.porchlights',
    'switch.livingroomlight_switch',
    'light.ge_45606_2way_dimmer_switch_level',
    'light.ge_45606_2way_dimmer_switch_level_2'
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
        self._log.info("Initializing DoorPanelHandler...")
        self._hass_secrets = self._get_hass_secrets()
        self.listen_event(
            self._handle_event, event='call_service'
        )
        self._leave_timer = None
