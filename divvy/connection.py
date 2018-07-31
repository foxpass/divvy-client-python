# Much of this file is based on
# https://github.com/andymccurdy/redis-py/blob/master/redis/connection.py,
# licensed under the MIT license.

from __future__ import absolute_import

import socket
import sys

from divvy.exceptions import ConnectionError, TimeoutError
from divvy.protocol import Translator


class Connection(object):
    def __init__(self, host='localhost', port=8321,
                 socket_timeout=1, socket_connect_timeout=1,
                 socket_keepalive=False, socket_keepalive_options=None,
                 socket_type=0, retry_on_timeout=False,
                 socket_read_size=1024, encoding='utf-8'):
        self.host = host
        self.port = port
        self.socket_timeout = socket_timeout
        self.socket_connect_timeout = socket_connect_timeout
        self.socket_keepalive = socket_keepalive
        self.socket_keepalive_options = socket_keepalive_options or {}
        self.socket_type = socket_type
        self.retry_on_timeout = retry_on_timeout
        self.socket_read_size = socket_read_size

        self._translator = Translator(encoding)
        self._sock = None

    def connect(self):
        """Connects to the Divvy server if not already connected."""

        if self._sock:
            return
        try:
            sock = self._connect()
        except socket.timeout:
            raise TimeoutError("Timeout connecting to server")
        except socket.error:
            e = sys.exc_info()[1]
            # args for socket.error can either be (errno, "message")
            # or just "message"
            if len(e.args) == 1:
                msg = "Error connecting to {}:{}. {}.".format(
                    self.host, self.port, e.args[0])
            else:
                msg = "Error {} connecting to {}:{}. {}.".format(
                    e.args[0], self.host, self.port, e.args[1])
            raise ConnectionError(msg)

        self._sock = sock

    def _connect(self):
        """Creates a TCP socket connection."""

        # we want to mimic what socket.create_connection does to support
        # ipv4/ipv6, but we want to set options prior to calling
        # socket.connect()
        err = None
        for res in socket.getaddrinfo(self.host, self.port, self.socket_type,
                                      socket.SOCK_STREAM):
            family, socktype, proto, canonname, socket_address = res
            sock = None
            try:
                sock = socket.socket(family, socktype, proto)
                # TCP_NODELAY
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

                # TCP_KEEPALIVE
                if self.socket_keepalive:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                    for k, v in self.socket_keepalive_options.items():
                        sock.setsockopt(socket.SOL_TCP, k, v)

                # set the socket_connect_timeout before we connect
                sock.settimeout(self.socket_connect_timeout)

                # connect
                sock.connect(socket_address)

                # set the socket_timeout now that we're connected
                sock.settimeout(self.socket_timeout)
                return sock

            except socket.error as _:
                err = _
                if sock is not None:
                    sock.close()

        if err is not None:
            raise err  # pylint: disable=raising-bad-type
        raise socket.error("socket.getaddrinfo returned an empty list")

    def disconnect(self):
        """Disconnects from the Divvy server."""

        if self._sock is None:
            return
        try:
            self._sock.shutdown(socket.SHUT_RDWR)
            self._sock.close()
        except socket.error:
            pass
        self._sock = None

    def send(self, msg):
        """Sends a command to the Divvy server."""
        if not self._sock:
            self.connect()
        try:
            self._sock.send(msg)
        except socket.timeout:
            self.disconnect()
            if self.retry_on_timeout:
                self.connect()
                try:
                    self._sock.send(msg)
                except socket.timeout:
                    self.disconnect()
                    raise TimeoutError("Timeout writing to socket after retry")
            else:
                raise TimeoutError("Timeout writing to socket")
        except socket.error:
            e = sys.exc_info()[1]
            self.disconnect()
            if len(e.args) == 1:
                errno, errmsg = 'UNKNOWN', e.args[0]
            else:
                errno = e.args[0]
                errmsg = e.args[1]
            raise ConnectionError("Error %s while writing to socket. %s." %
                                  (errno, errmsg))
        except Exception as e:
            self.disconnect()
            raise e

    def recv(self):
        """Receives a response from the Divvy server. This should only be
        called immediately after a command is sent."""
        try:
            response = self._sock.recv(self.socket_read_size)
            if not response:
                raise ConnectionError("Connection closed by server.")
        except Exception as e:
            self.disconnect()
            raise e
        return response
