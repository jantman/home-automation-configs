#!/usr/bin/env python3

import requests
import json
import os
from collections import defaultdict

hass_token = os.environ['TOKEN']
host = os.environ.get('HASS_HOST', '127.0.0.1')
r = requests.get(
    f'http://{host}:8123/api/states',
    headers={'Authorization': f'Bearer {hass_token}'}
)
r.raise_for_status()
states = r.json()
nodes = defaultdict(list)
result = {}
for s in states:
    if s['entity_id'].startswith('zwave.'):
        for k in ['last_changed', 'last_updated']:
            s.pop(k, None)
        for k in list(s['attributes'].keys()):
            if k.startswith('sent') or k.startswith('received') or k.startswith('lastR') or k == 'retries':
                s['attributes'].pop(k, None)
        result[s['attributes']['node_id']] = s
    if 'node_id' in s['attributes']:
        nodes[s['attributes']['node_id']].append(s['entity_id'])
for n, l in nodes.items():
    if n not in result:
        result[n] = {}
    result[n]['related'] = l

with open('zwave_nodes.json', 'w') as fh:
    json.dump(result, fh, sort_keys=True, indent=4)
