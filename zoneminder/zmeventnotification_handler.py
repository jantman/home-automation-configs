#!/usr/bin/env python3
"""
ZoneMinder event handler client. This is a BAD retrofit to my previous code.

Connects to the zmeventnotification websocket server and executes a command for
every event.
"""

import asyncio
import websockets

async def handle():
    uri = "ws://localhost:9000"
    print('Connecting to: %s' % uri)
    async with websockets.connect(uri) as websocket:
        print('Connected')
        """
        print('Connected; sending version request')
        await websocket.send('{"event":"control","data":{"type":"version"}}')
        response = await websocket.recv()
        print('Version response: %s' % response)
        """
        auth = '{"event":"auth","data":{"user":"u","password":"p"}}'
        print('Sending auth message: %s', auth)
        await websocket.send(auth)
        print('Waiting for auth response...')
        response = await websocket.recv()
        print('Auth response: %s' % response)
        print('Listening for messages...')
        while True:
            message = await websocket.recv()
            print('Got message: %s' % message)

while True:
    print('Running outer loop...')
    asyncio.get_event_loop().run_until_complete(handle())
