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
    async with websockets.connect(uri) as websocket:
        name = input("What's your name? ")

        await websocket.send(name)
        print(f"> {name}")

        greeting = await websocket.recv()
        print(f"< {greeting}")

asyncio.get_event_loop().run_until_complete(handle())
