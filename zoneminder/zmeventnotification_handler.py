#!/usr/bin/env python3
"""
ZoneMinder event handler client. This is a BAD retrofit to my previous code.

Connects to the zmeventnotification websocket server and executes a command for
every event.

Event examples:
{"event":"alarm","type":"","status":"Success","events":[{"MonitorId":"2","Cause":"","EventId":"457722","Name":"SOUTH","RulesObject":{},"DetectionJson":[]}]}
{"status":"Success","events":[{"Name":"NORTH","DetectionJson":[],"RulesObject":{},"Cause":"","MonitorId":"1","EventId":"457723"}],"type":"","event":"alarm"}
{"type":"","event":"alarm","events":[{"DetectionJson":[],"RulesObject":{},"Name":"SOUTH","EventId":"457722","Cause":"End:Motion: All","MonitorId":"2"}],"status":"Success"}
{"status":"Success","events":[{"MonitorId":"1","Cause":"End:Motion: All","EventId":"457723","Name":"NORTH","RulesObject":{},"DetectionJson":[]}],"event":"alarm","type":""}

"""

import json
import asyncio
import websockets
import logging

FORMAT = "[%(asctime)s %(levelname)s] %(message)s"
logging.basicConfig(level=logging.INFO, format=FORMAT)
logger = logging.getLogger()


async def handle():
    uri = "ws://localhost:9000"
    logger.info('Connecting to: %s', uri)
    async with websockets.connect(uri, ping_interval=10, ping_timeout=None) as websocket:
        logger.info('Connected')
        auth = '{"event":"auth","data":{"user":"u","password":"p"}}'
        logger.info('Sending auth message: %s', auth)
        await websocket.send(auth)
        logger.info('Waiting for auth response...')
        response = await websocket.recv()
        logger.info('Auth response: %s', response)
        rj = json.loads(response)
        # {"type":"","event":"auth","status":"Success","version":"6.0.6","reason":""}
        if rj['event'] != 'auth' or rj['status'] != 'Success':
            raise RuntimeError("ERROR: Bad auth")
        logger.info('sending version request')
        await websocket.send('{"event":"control","data":{"type":"version"}}')
        response = await websocket.recv()
        logger.info('Version response: %s', response)
        logger.info('Listening for messages...')
        while True:
            message = await asyncio.wait_for(websocket.recv(), timeout=60)
            logger.info('Got message: %s', message)

while True:
    logger.info('Running outer loop...')
    try:
        asyncio.get_event_loop().run_until_complete(handle())
    except websockets.exceptions.ConnectionClosed:
        logger.error('ERROR: Connection closed', exc_info=True)
