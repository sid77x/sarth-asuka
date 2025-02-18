# MIT License

# Copyright (c) 2022 Sarthak

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from __future__ import annotations

import asyncio
import json
import sys
import time
import typing

import aiohttp

from asuka import events

from .enums import WSEventEnums
from .events import EventParser
from .keep_alive import KeepAlive

if typing.TYPE_CHECKING:
    from asuka.bot import Bot


class Gateway:
    __slots__: typing.Tuple[str, ...] = ("_bot", "_keep_alive", "_latency", "_heartbeat_interval", "_socket")

    def __init__(self, bot: "Bot") -> None:
        self._bot = bot
        self._keep_alive = KeepAlive()
        self._latency: float = 0
        self._heartbeat_interval: float = 0
        self._socket: aiohttp.ClientWebSocketResponse

    @property
    def socket(self) -> aiohttp.ClientWebSocketResponse:
        return self._socket

    @property
    def keep_alive(self) -> KeepAlive:
        return self._keep_alive

    @property
    def latency(self) -> float:
        return self._latency

    @property
    def identify_payload(self) -> typing.Dict[str, typing.Any]:
        return {
            "op": 2,
            "d": {
                "token": self._bot.rest._token,
                "intents": self._bot.intents.value,
                "properties": {
                    "$os": sys.platform,
                    "$browser": "clyde",
                    "$device": "clyde",
                },
            },
        }

    async def listen_gateway(self) -> None:
        async for message in self.socket:
            if message.type == aiohttp.WSMsgType.TEXT:
                await self._parse_payload_response(json.loads(message.data))

    async def _get_socket_ready(self) -> None:
        self._socket = await self._bot.rest._create_websocket()

    async def _hello_res(self, d: typing.Dict[str, typing.Any]) -> None:
        await self.socket.send_json(self.identify_payload)
        self._heartbeat_interval = d["heartbeat_interval"] / 1000
        loop = asyncio.get_event_loop()
        loop.create_task(self.keep_alive.start(self))

    async def _dispatch_events(self, payload: typing.Dict[str, typing.Any]) -> None:
        if payload["t"] == "MESSAGE_CREATE":
            self._bot._event_handler.dispatch(events.MessageCreate, EventParser.message_create(self._bot, payload))
            return

    async def _parse_payload_response(self, payload: typing.Dict[str, typing.Any]) -> None:
        op, t, d = payload["op"], payload["t"], payload["d"]
        if op == WSEventEnums.HEARTBEAT_ACK:
            self._latency = time.perf_counter() - self.keep_alive.last_heartbeat
            return

        if op == WSEventEnums.HELLO:
            await self._hello_res(d)

        elif op == WSEventEnums.DISPATCH:
            self.keep_alive.sequence += 1
            await self._dispatch_events(payload)
