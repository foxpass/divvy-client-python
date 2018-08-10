from __future__ import absolute_import

from collections import namedtuple
import re
import socket

from divvy.connection import Connection
from divvy.exceptions import InputError
from divvy.protocol import Translator


class DivvyClient(object):
    def __init__(self, host='localhost', port=8321,
                 socket_timeout=1, socket_connect_timeout=1,
                 socket_keepalive=False, socket_keepalive_options=None,
                 socket_type=0, retry_on_timeout=False, encoding='utf-8'):
        self.host = host
        self.port = port
        self.translator = Translator(encoding=encoding)
        self.connection = Connection(
            host=host,
            port=port,
            socket_timeout=socket_timeout,
            socket_connect_timeout=socket_connect_timeout,
            socket_keepalive=socket_keepalive,
            socket_keepalive_options=socket_keepalive_options,
            socket_type=socket_type,
            retry_on_timeout=retry_on_timeout
        )

    def check_rate_limit(self, **kwargs):
        """Perform a check-and-decrement of quota. Zero or more key-value pairs
        specify the operation being performed, and will be evaluated by the
        server against its configuration."""
        cmd = self.translator.build_hit(**kwargs)
        self.connection.send(cmd)

        reply = self.connection.recv()
        response = self.translator.parse_reply(reply)
        return response
