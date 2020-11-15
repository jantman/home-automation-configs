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
        print('Connected; sending version request')
        await websocket.send('{"event":"control","data":{"type":"version"}}')
        response = await websocket.recv()
        print('Version response: %s' % response)
        print('Listening for messages...')
        async for message in websocket:
            print('Got message: %s' % message)

asyncio.get_event_loop().run_until_complete(handle())
