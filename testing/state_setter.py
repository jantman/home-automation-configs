#!/usr/bin/env python

import requests
from copy import deepcopy
from termcolor import colored

INITIAL_STATES = {
    'binary_sensor.bedroom_motion': {
        'attributes': {
            'device_class': 'motion',
            'friendly_name': 'Bedroom Motion'
        },
        'entity_id': 'binary_sensor.bedroom_motion',
        'state': 'off'
    },
    'binary_sensor.ecolink_doorwindow_sensor_sensor': {
        'attributes': {
            'device_class': 'door',
            'friendly_name': 'FrontDoor'
        },
        'entity_id': 'binary_sensor.ecolink_doorwindow_sensor_sensor',
        'state': 'off'
    },
    'binary_sensor.ecolink_doorwindow_sensor_sensor_2': {
        'attributes': {
            'device_class': 'door',
            'friendly_name': 'Crawlspace',
        },
        'entity_id': 'binary_sensor.ecolink_doorwindow_sensor_sensor_2',
        'state': 'off'
    },
    'binary_sensor.ecolink_doorwindow_sensor_sensor_3': {
        'attributes': {
            'device_class': 'door',
            'friendly_name': 'Gate'
        },
        'entity_id': 'binary_sensor.ecolink_doorwindow_sensor_sensor_3',
        'state': 'off'
    },
    'binary_sensor.ecolink_doorwindow_sensor_sensor_4': {
        'attributes': {
            'device_class': 'door',
            'friendly_name': 'KitchenDoor'
        },
        'entity_id': 'binary_sensor.ecolink_doorwindow_sensor_sensor_4',
        'state': 'off'
    },
    'binary_sensor.ecolink_motion_detector_sensor': {
        'attributes': {
            'device_class': 'motion',
            'friendly_name': 'Back Bedroom Motion',
        },
        'entity_id': 'binary_sensor.ecolink_motion_detector_sensor',
        'state': 'off'
    },
    'binary_sensor.kitchen_motion': {
        'attributes': {
            'device_class': 'motion',
            'friendly_name': 'Kitchen Motion'
        },
        'entity_id': 'binary_sensor.kitchen_motion',
        'state': 'off'
    },
    'binary_sensor.livingroom_motion': {
        'attributes': {
            'device_class': 'motion',
            'friendly_name': 'Living Room Motion'
        },
        'entity_id': 'binary_sensor.livingroom_motion',
        'state': 'off'
    },
    'binary_sensor.office_motion': {
        'attributes': {
            'device_class': 'motion',
            'friendly_name': 'Office Motion'
        },
        'entity_id': 'binary_sensor.office_motion',
        'state': 'off'
    },
    'device_tracker.rf8m22eq54n': {
        'attributes': {
            'activity': '',
            'altitude': 0.0,
            'battery': 99.0,
            'direction': 0.0,
            'friendly_name': 'GalaxyS10',
            'gps_accuracy': 20,
            'latitude': 33.7537428,
            'longitude': -84.2456995,
            'provider': 'network',
            'source_type': 'gps',
            'speed': 0.0
        },
        'entity_id': 'device_tracker.rf8m22eq54n',
        'state': 'home'
    },
    'input_select.alarmstate': {
        'attributes': {
            'friendly_name': 'Alarm State',
            'options': ['Home',
                        'Away',
                        'Disarmed']
        },
        'entity_id': 'input_select.alarmstate',
        'state': 'Disarmed'
    },
    'light.linear_lb60z1_dimmable_led_light_bulb_level': {
        'attributes': {
            'brightness': 85,
            'friendly_name': 'KitchenBulb',
            'max_mireds': 500,
            'min_mireds': 153,
            'node_id': 14,
            'supported_features': 1,
            'value_id': '72057594277625857',
            'value_index': 0,
            'value_instance': 1
        },
        'entity_id': 'light.linear_lb60z1_dimmable_led_light_bulb_level',
        'state': 'off'
    },
    'light.linear_lb60z1_dimmable_led_light_bulb_level_2': {
        'attributes': {
            'brightness': 93,
            'friendly_name': 'KitchenBulb2 '
                             'Level',
            'max_mireds': 500,
            'min_mireds': 153,
            'node_id': 16,
            'supported_features': 1,
            'value_id': '72057594311180289',
            'value_index': 0,
            'value_instance': 1
        },
        'entity_id': 'light.linear_lb60z1_dimmable_led_light_bulb_level_2',
        'state': 'off'
    },
    'light.linear_lb60z1_dimmable_led_light_bulb_level_3': {
        'attributes': {
            'friendly_name': 'PorchBulb2 '
                             'Level',
            'node_id': 17,
            'supported_features': 1,
            'value_id': '72057594327957505',
            'value_index': 0,
            'value_instance': 1
        },
        'entity_id': 'light.linear_lb60z1_dimmable_led_light_bulb_level_3',
        'state': 'off'
    },
    'light.zipato_bulb_2_level': {
        'attributes': {
            'friendly_name': 'PorchBulb',
            'node_id': 13,
            'supported_features': 49,
            'value_id': '72057594260848641',
            'value_index': 0,
            'value_instance': 1
        },
        'entity_id': 'light.zipato_bulb_2_level',
        'state': 'off'
    },
    'proximity.home': {
        'attributes': {
            'dir_of_travel': 'arrived',
            'friendly_name': 'home',
            'nearest': 'GalaxyS10',
            'unit_of_measurement': 'm'
        },
        'entity_id': 'proximity.home',
        'state': '0'
    },
    'sun.sun': {
        'attributes': {
            'friendly_name': 'Sun'
        },
        'entity_id': 'sun.sun',
        'state': 'above_horizon'
    },
    'switch.livingroomlight_switch': {
        'attributes': {
            'friendly_name': 'LivingRoomLight '
                             'Switch',
            'node_id': 15,
            'value_id': '72057594294386688',
            'value_index': 0,
            'value_instance': 1
        },
        'entity_id': 'switch.livingroomlight_switch',
        'state': 'off'
    }
}


class StateSetter(object):

    def __init__(self):
        self._states = deepcopy(INITIAL_STATES)
        self._entities = {
            a[0]: a[1] for a in enumerate(sorted(self._states.keys()))
        }

    def _update_states(self):
        r = requests.get('http://127.0.0.1:8123/api/states')
        for s in r.json():
            if s['entity_id'] in self._states:
                self._states[s['entity_id']] = s

    def run(self):
        while True:
            self._prompt()

    def _set_state(self, entity_id, entity=None):
        if entity is None:
            entity = self._states[entity_id]
        print('Setting state of %s (%s) to: %s' % (
            entity['attributes']['friendly_name'],
            entity_id,
            entity['state']
        ))
        s = deepcopy(entity)
        del s['entity_id']
        r = requests.post(
            'http://127.0.0.1:8123/api/states/%s' % entity_id,
            headers={'Content-Type': 'application/json'},
            json=s
        )
        r.raise_for_status()

    def _set_initial(self):
        for k in INITIAL_STATES.keys():
            self._set_state(k, INITIAL_STATES[k])

    def _handle_input_select(self, entity_id, entity):
        for idx, val in enumerate(entity['attributes']['options']):
            print('\t%d) %s' % (idx, val))
        res = input('\tSelection: ').strip()
        sel = int(res)
        self._states[entity_id]['state'] = entity['attributes']['options'][sel]
        return self._set_state(entity_id)

    def _handle_input_proximity(self, entity_id, _):
        res = input('Enter distance in meters: ').strip()
        self._states[entity_id]['state'] = res
        return self._set_state(entity_id)

    def _handle_selection(self, selection):
        if selection == 'q':
            raise SystemExit(1)
        if selection == '':
            return
        if selection == 'i':
            self._set_initial()
            return
        try:
            selection = int(selection)
        except Exception:
            return
        if selection not in self._entities:
            return
        # ok, we have a valid selection
        entity_id = self._entities[selection]
        entity = self._states[entity_id]
        if entity['state'] == 'on':
            self._states[entity_id]['state'] = 'off'
            return self._set_state(entity_id)
        if entity['state'] == 'off':
            self._states[entity_id]['state'] = 'on'
            return self._set_state(entity_id)
        if entity_id.startswith('input_select.'):
            return self._handle_input_select(entity_id, entity)
        if entity_id == 'sun.sun':
            if entity['state'] == 'below_horizon':
                self._states[entity_id]['state'] = 'above_horizon'
            else:
                self._states[entity_id]['state'] = 'below_horizon'
            return self._set_state(entity_id)
        if entity_id.startswith('proximity.'):
            return self._handle_input_proximity(entity_id, entity)
        if entity_id.startswith('device_tracker.'):
            if entity['state'] == 'home':
                self._states[entity_id]['state'] = 'away'
            else:
                self._states[entity_id]['state'] = 'home'
            return self._set_state(entity_id)
        raise RuntimeError('Unknown entity ID format/type')

    def _prompt(self):
        self._update_states()
        for idx, entity_id in sorted(self._entities.items()):
            fn = self._states[entity_id].get(
                'attributes', {}
            ).get('friendly_name', None)
            if entity_id.startswith('proximity.'):
                fn = entity_id
            st = self._states[entity_id]['state']
            if st == 'on':
                st = colored('ON', 'green')
            elif st == 'off':
                st = colored('OFF', 'red')
            print('%2d) %s (%s)' % (idx, fn, st))
        print('          i)  set initial states (all)')
        print('          q)  quit')
        print('   <Return> - Refresh states')
        res = input('Selection: ').strip()
        self._handle_selection(res)
        print('\n\n\n')


if __name__ == "__main__":
    StateSetter().run()
