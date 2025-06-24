# THIS FILE IS PART OF THE CYLC WORKFLOW ENGINE.
# Copyright (C) NIWA & British Crown (Met Office) & Contributors.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""Publisher for workflow runtime API."""

import asyncio
from typing import (
    Callable, NamedTuple, Optional, Set, Union
)

import zmq

from cylc.flow import LOG
from cylc.flow.network import ZMQSocketBase


class PublisherItem(NamedTuple):
    """Item of publisher queue.

    Fields:
        topic: The topic of the message.
        data: Data element/message to serialise and send.
        serializer: string/func for encoding.
    """
    topic: bytes
    data: object
    serializer: Optional[str] = None


def serialize_data(
    data: object, serializer: Union[Callable, str, None], *args, **kwargs
) -> object:
    """Serialize by specified method."""
    if callable(serializer):
        return serializer(data, *args, **kwargs)
    if isinstance(serializer, str):
        return getattr(data, serializer)(*args, **kwargs)
    return data


class WorkflowPublisher(ZMQSocketBase):
    """Initiate the PUB part of a ZMQ PUB-SUB pair.

    This class contains the logic for the ZMQ message Publisher.

    Usage:
        * Call publish to send items to subscribers.

    """

    def __init__(self, workflow: str, context: Optional[zmq.Context] = None):
        super().__init__(zmq.PUB, workflow, bind=True, context=context)
        self.topics: Set[bytes] = set()

    def _socket_options(self):
        """Set socket options after socket instantiation and before bind.

        Overwrites Base method.

        """
        # this limit on messages in queue is more than enough,
        # as messages correspond to scheduler loops (*messages/loop):
        self.socket.sndhwm = 1000

    def _bespoke_stop(self):
        """Bespoke stop items."""
        LOG.debug('stopping zmq publisher...')
        self.stopping = True

    async def send_multi(self, item: PublisherItem) -> None:
        """Send multi part message."""
        if self.socket:
            self.topics.add(item.topic)
            self.socket.send_multipart(
                [item.topic, serialize_data(item.data, item.serializer)]
            )
        # else we are in the process of shutting down - don't send anything

    async def publish(self, *items: PublisherItem) -> None:
        """Publish topics.

        Args:
            items (iterable): [(topic, data, serializer)]

        """
        try:
            # await gather_coros(self.send_multi, items)
            await asyncio.gather(
                *(self.send_multi(item) for item in items)
            )
        except Exception as exc:
            LOG.error(f"publish - {type(exc).__name__}: {exc}")
