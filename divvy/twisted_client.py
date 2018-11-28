import os
import sys
from collections import deque

from twisted.internet import reactor
from twisted.internet.defer import Deferred, succeed, fail
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
    log = Logger()

    def __init__(self, host, port, timeout=1.0, encoding='utf-8'):
        """
        Configures a client that can speak to a Divvy rate limiting server.
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.encoding = encoding
        self.connection = None
        # this may be a unwanted side effect for a constructor
        # it is kept anyway to maintain the existing behavior without
        # changing the api
        self.connect() 

    def connect(self):
        """Connect to the server.
        disconnect and reconnect if connection already exists

        :return: deferred twisted protocol instance on connection made
        """
        if self.connection:
            self.disconnect()
        self.connection = self._makeConnection()
        return self.connection.deferred

    def disconnect(self):
        """Disconnect cleanly
        """
        if self.connection:
            self.connection.close()
            self.connection = None

    def check_rate_limit(self, timeout=None, **hit_args):
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
        assert self.connection, "client disconnected"
        if timeout is None:
            return self.connection.checkRateLimit(hit_args)
        else:
            d = self.connection.deferred
            d.addCallback(self.connection.checkRateLimit, hit_args)
            d.addTimeout(timeout)
            return d

    def _makeConnection(self):
        factory = DivvyFactory(self.timeout, self.encoding)
        reactor.connectTCP(self.host, self.port, factory, self.timeout)
        return factory
     

class DivvyProtocol(LineOnlyReceiver):
    log = Logger()
    """
    Twisted handler for network communication with a Divvy server.
    """

    delimiter = b'\n'

    def connectionMade(self):
        self.factory.deferred.callback(self)

    def checkRateLimit(self, **kwargs):
        assert self.connected
        line = self.factory.translator.build_hit(**kwargs).strip()
        # self.log.debug("tx: {line}", line=line)
        self.sendLine(line)
        return self

    def lineReceived(self, line):
        # self.log.debug("rx: {line}", line=line)
        deferred = self.factory.deferredResponses.popleft()
        try:
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
    
    def __init__(self, timeout=1.0, encoding='utf-8'):
        self.timeout = timeout
        self.translator = Translator(encoding)
        self.deferred = Deferred()
        self.deferredResponses = deque()
        self.divvyProtocol = None
        self.running = True
        self.addr = None

    def buildProtocol(self, addr):
        self.resetDelay()
        self.addr = addr
        self.divvyProtocol = ReconnectingClientFactory.buildProtocol(self, addr)
        return self.divvyProtocol
        
    def checkRateLimit(self, hit_args):
        if self.divvyProtocol is None:
            # fail immediatelly if not connected
            return fail(ConnectionLost("on checkRateLimit"))
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
            self.log.error("request timeout {err}", err=err)
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
        if not self.deferred.called:
            self.deferred.errback(reason)
        self.deferred = Deferred()
        self.divvyProtocol = None

        # cleanup all pending responses 
        while self.deferredResponses:
            d = self.deferredResponses.popleft()
            d.errback(reason)

        # retry if required
        if self.running:
            ReconnectingClientFactory.retry(self, connector)

    def clientConnectionLost(self, connector, reason):
        if reason.check(ConnectionDone) and not self.running:
            # shall not have pending responses on regular disconnection
            assert not self.deferredResponses
        self.log.info("connection lost: {reason}", reason=reason )
        self.retry(connector, reason)

    def clientConnectionFailed(self, connector, reason):
        self.log.error("connection failed: {reason}", reason=reason )
        self.retry(connector, reason)



__all__ = ["DivvyClient"]
