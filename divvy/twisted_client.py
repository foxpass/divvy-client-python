import os
import sys
from collections import deque

from twisted.internet import reactor
from twisted.internet.defer import Deferred, succeed
from twisted.internet.protocol import ReconnectingClientFactory
from twisted.internet.endpoints import TCP4ClientEndpoint, connectProtocol
from twisted.internet.error import TimeoutError, ConnectionDone
from twisted.internet.task import deferLater
from twisted.python import log
from twisted.python.failure import Failure
from twisted.protocols.basic import LineOnlyReceiver
from twisted.protocols.policies import TimeoutMixin

from divvy.protocol import Translator


translator = Translator()
if os.getenv("DEBUG") == "1":
    log.startLogging(sys.stdout)


class DivvyClient(object):
    def __init__(self, host, port, timeout=1.0, encoding='utf-8'):
        """
        Configures a client that can speak to a Divvy rate limiting server.
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.encoding = encoding
        self.connection = None

    def check_rate_limit(self, **hit_args):
        """
        Perform a check-and-decrement of quota. This will establish a new
        connection for each request, because connection pooling and reuse is
        so freakin' complicated in Twisted. :(

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
        connection = self._getConnection()
        return connection.checkRateLimit(hit_args)

    def close(self):
        self.connection.close()

    def _getConnection(self):
        """Return existing connection or create one
        """
        if self.connection is None:
            self.connection = self._makeConnection()
        return self.connection

    def _makeConnection(self):
        """Return existing connection or create one
        """
        factory = DivvyFactory(self.timeout, self.encoding)
        reactor.connectTCP(self.host, self.port, factory, self.timeout)
        return factory
     

class DivvyProtocol(LineOnlyReceiver):
    """
    Twisted handler for network communication with a Divvy server.
    """

    delimiter = "\n"

    def connectionMade(self):
        self.factory.connection.callback(self)

    def checkRateLimit(self, **kwargs):
        assert self.connected
        line = self.factory.translator.build_hit(**kwargs).strip()
        log.msg("tx:", line)
        self.sendLine(line)
        return self

    def lineReceived(self, line):
        log.msg("rx: ", line)
        deferred = self.factory.deferredResponses.popleft()
        try:
            response = self.factory.translator.parse_reply(line)
            deferred.callback(response)
        except Exception as e:
            deferred.errback(e)


class DivvyFactory(ReconnectingClientFactory):
    """Handle the connection

    - Reconnect if connection drops
    - Produce DivvyProtocol instances on connection
    """
    protocol = DivvyProtocol
    
    def __init__(self, timeout=1.0, encoding='utf-8'):
        self.timeout = timeout
        self.translator = Translator(encoding)
        self.connection = Deferred()
        self.deferredResponses = deque()
        self.transport = None
        self.running = True

    def checkRateLimit(self, hit_args):
        def makeRequest(divvyProtocol):
            self.transport = divvyProtocol.transport
            return divvyProtocol.checkRateLimit(**hit_args)
        self.connection.addCallback(makeRequest)
        return self.newDeferredResponse()

    def newDeferredResponse(self):
        d = Deferred()
        d.addTimeout(self.timeout, reactor)
        d.addErrback(self.cleanupOnTimeout, d)
        self.deferredResponses.append(d)
        return d

    def cleanupOnTimeout(self, err, d):
        if isinstance(err, TimeoutError):
            log.msg("request timeout", e)
            # O(n) worst case, O(1) if all timeouts are the same
            self.deferredResponses.remove(d)
        return err

    def close(self):
        self.running = False
        self.stopTrying()
        if self.transport:
            self.transport.loseConnection()
    
    def retry(self, connector, reason):
        while self.deferredResponses:
            d = self.deferredResponses.popleft()
            d.errback(reason)
        if not self.connection.called:
            d = self.connection
            d.errback(reason)
        if self.running:
            self.connection = Deferred()
            ReconnectingClientFactory.retry(self, connector)

    def clientConnectionLost(self, connector, reason):
        if reason.check(ConnectionDone) and not self.running:
            assert not self.deferredResponses
        log.msg("connection lost: ", reason )
        self.retry(connector, reason)

    def clientConnectionFailed(self, connector, reason):
        log.msg("connection failed: ", reason )
        self.retry(connector, reason)



__all__ = ["DivvyClient"]