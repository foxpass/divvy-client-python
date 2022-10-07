import os
import sys
from collections import deque

from twisted.internet import defer, reactor
from twisted.internet.defer import Deferred
from twisted.internet.protocol import ReconnectingClientFactory
from twisted.internet.endpoints import TCP4ClientEndpoint, connectProtocol
from twisted.internet.error import TimeoutError, ConnectionDone, ConnectionLost
from twisted.internet.task import deferLater
from twisted.logger import Logger
from twisted.python import log
from twisted.python.failure import Failure
from twisted.protocols.basic import LineOnlyReceiver
from twisted.protocols.policies import TimeoutMixin

from divvy.protocol import Translator


translator = Translator()

class DivvyClient(object):
    log = Logger(__name__)

    def __init__(self, host, port, timeout=1.0, encoding='utf-8', debug_mode=False, count_before_reconnect=1000):
        """
        Configures a client that can speak to a Divvy rate limiting server.
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.encoding = encoding
        self.connected = False
        self.factory = DivvyFactory(self, self.timeout, self.encoding, debug_mode, count_before_reconnect=count_before_reconnect)
        reactor.connectTCP(self.host, self.port, self.factory)
        self.debug_mode = debug_mode


    def check_rate_limit(self, timeout=None, **hit_args):
        """
        Perform a check-and-decrement of quota.

        Args:
             **kwargs: Zero or more key-value pairs to specify the operation
                being performed, which will be evaluated by the server against
                its configuration.

        Returns:
            twisted.internet.defer.Deferred: Callbacks will be executed when we
                hear back from the server. Callbacks will receive a single
                divvy.Response with these fields:
                    is_allowed: one of true, false, indicating whether quota
                        was available.
                    current_credit: number of credit(s) available at the end
                        of this command.
                    next_reset_seconds: time, in seconds, until credit next
                        resets.
        """
        if not self.connected:
            # TODO: if not connected, wait `timeout` seconds for the socket to be connected,
            # (e.g. factory.connection_made_deferred is triggered) and then call
            # checkRateLimit (look into defer.chainDeferred())
            return defer.fail(ConnectionLost("Not yet connected"))

        return self.factory.checkRateLimit(hit_args)


class DivvyProtocol(LineOnlyReceiver):
    log = Logger(__name__)
    count = 0
    """
    Twisted handler for network communication with a Divvy server.
    """

    delimiter = b'\n'

    def __init__(self, *args, **kwargs):
        if 'count_before_reconnect' in kwargs:
            self.count = kwargs['count_before_reconnect']
            kwargs.pop('count_before_reconnect')
        super().__init__(*args, **kwargs)

    def setReconnectCount(self, count):
        self.max_count = count

    def connectionMade(self):
        self.log.info("Protocol.connectionMade")

    def checkRateLimit(self, **kwargs):
        assert self.connected
        self.count = self.count + 1
        if self.count > self.max_count:
            self.count = 0
            self.transport.loseConnection()

        line = self.factory.translator.build_hit(**kwargs).strip()
        if self.debug_mode:
            self.log.debug("DivvyClient: Sent {line}", line=line)
        self.sendLine(line)
        return self

    def lineReceived(self, line):
        deferred = self.factory.deferredResponses.popleft()
        try:
            if self.debug_mode:
                self.log.debug("DivvyClient: Received {line}", line=line)
            response = self.factory.translator.parse_reply(line)
            deferred.callback(response)
        except Exception as e:
            deferred.errback(e)


class DivvyFactory(ReconnectingClientFactory):
    log = Logger()

    """Handle the connection

    - Reconnect if connection drops
    - Produce DivvyProtocol instances on connection
    """
    protocol = DivvyProtocol

    def __init__(self, divvy_client, timeout=1.0, encoding='utf-8', debug_mode=False, count_before_reconnect=10000):
        self.divvy_client = divvy_client
        self.timeout = timeout
        self.translator = Translator(encoding)
        self.connection_made_deferred = Deferred()
        self.deferredResponses = deque()
        self.divvyProtocol = None
        self.running = True
        self.addr = None
        self.debug_mode = debug_mode
        self.count_before_reconnect = count_before_reconnect

    def buildProtocol(self, addr):
        self.resetDelay()
        self.addr = addr
        self.divvyProtocol = ReconnectingClientFactory.buildProtocol(self, addr)
        self.divvyProtocol.setReconnectCount(self.count_before_reconnect)
        self.divvyProtocol.debug_mode = self.debug_mode
        self.divvy_client.connected = True
        self.connection_made_deferred.callback(True)
        return self.divvyProtocol

    def checkRateLimit(self, hit_args):
        if self.divvyProtocol is None:
            # fail immediately if not connected
            return defer.fail(ConnectionLost("on checkRateLimit"))
        if self.debug_mode:
            self.log.debug("DivvyClient: Checking ratelimit {hit_args}", hit_args=hit_args)
        self.divvyProtocol.checkRateLimit(**hit_args)
        return self.newDeferredResponse()

    def newDeferredResponse(self):
        """Make a lifetime limited response and save it in a FIFO queue

        Responses are associated to requests based only in the order
        assuming the server send reponses in the same order as it receive requests
        """
        d = Deferred()
        d.addTimeout(self.timeout, reactor)
        d.addErrback(self.cleanupOnTimeout, d)
        self.deferredResponses.append(d)
        return d

    def cleanupOnTimeout(self, err, d):
        """Called when a deferred response timeouts to remove it from the FIFO queue
        """
        if isinstance(err, TimeoutError):
            self.log.error("DivvyClient: request timeout {err}", err=err)
            # O(n) worst case, O(1) if all timeouts are the same
            self.deferredResponses.remove(d)
        return err

    def close(self, *_):
        # self.log.debug("client connection closed properly")
        self.running = False
        self.stopTrying()  # cancel possible reconnection delayed call
        if self.divvyProtocol:
            self.divvyProtocol.transport.loseConnection()

    def retry(self, connector, reason):
        # notify client of connection failure
        self.connection_made_deferred = Deferred()
        self.divvyProtocol = None

        # cleanup all pending responses
        while self.deferredResponses:
            d = self.deferredResponses.popleft()
            d.errback(reason)

        # retry if required
        if self.running:
            ReconnectingClientFactory.retry(self, connector)

    def startedConnecting(self, connector):
        self.log.info('Started to connect.')

    def clientConnectionLost(self, connector, reason):
        self.divvy_client.connected = False
        if reason.check(ConnectionDone) and not self.running:
            # shall not have pending responses on regular disconnection
            assert not self.deferredResponses
        self.log.info("DivvyClient: connection lost {reason}", reason=reason )
        self.retry(connector, reason)

    def clientConnectionFailed(self, connector, reason):
        self.log.error("DivvyClient: connection failed {reason}", reason=reason )
        self.retry(connector, reason)



__all__ = ["DivvyClient"]
