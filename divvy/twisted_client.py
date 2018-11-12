import sys

from twisted.internet import reactor
from twisted.internet.defer import Deferred, succeed
from twisted.internet.protocol import ReconnectingClientFactory
from twisted.internet.endpoints import TCP4ClientEndpoint, connectProtocol
from twisted.internet.error import TimeoutError
from twisted.internet.task import deferLater
from twisted.python import log
from twisted.python.failure import Failure
from twisted.protocols.basic import LineOnlyReceiver
from twisted.protocols.policies import TimeoutMixin

from divvy.protocol import Translator


translator = Translator()
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

    def _getConnection(self):
        """Return existing connection or create one
        """
        if self.connection is None:
            self.connection = self._makeConnection()
        return self.connection

    def _makeConnection(self):
        """Return existing connection or create one
        """
        factory = DivvyFactory( self.encoding )
        reactor.connectTCP( self.host, self.port, factory, self.timeout )
        return factory
     

class DivvyProtocol(LineOnlyReceiver, TimeoutMixin, object):
    """
    Twisted handler for network communication with a Divvy server.
    """

    delimiter = "\n"

    def __init__(self, timeout=1.0, encoding='utf-8'):
        super(DivvyProtocol, self).__init__()
        self.timeout = timeout
        self.translator = Translator(encoding)

    def connectionMade(self):
        self.factory.connection.callback(self)

    def timeoutConnection(self):
        TimeoutMixin.timeoutConnection(self)
        self.factory.connection.errback(TimeoutError())

    def checkRateLimit(self, **kwargs):
        assert self.connected
        line = self.translator.build_hit(**kwargs).strip()
        log.msg("tx:", line)
        self.sendLine(line)
        self.setTimeout(self.timeout)
        return self

    def lineReceived(self, line):
        self.setTimeout(None)
        deferred = self.factory.deferredResponses.pop()
        try:
            response = self.translator.parse_reply(line)
            deferred.callback(response)
        except Exception as e:
            deferred.errback(e)


class DivvyFactory(ReconnectingClientFactory):
    """Handle the connection

    - Reconnect if connection drops
    - Produce DivvyProtocol instances on connection
    """
    protocol = DivvyProtocol
    
    def __init__(self, encoding):
        self.encoding = encoding
        self.connection = Deferred()
        self.deferredResponses = list()

    def checkRateLimit(self, hit_args):
        def makeRequest(protocol):
           return protocol.checkRateLimit(**hit_args)
        self.connection.addCallback(makeRequest)
        d = Deferred()
        self.deferredResponses.append(d)
        return d

    def _onConnectionFail(self, reason):
        d = self.connection
        self.connection = Deferred()
        log.debug("connection failure: {}", reason )
        d.errBack(reason)
    
    def clientConnectionLost(self, connector, reason):
        self._onConnectionFail(reason)
        ReconnectingClientFactory.clientConnectionLost(self, connector, reason)

    def clientConnectionFailed(self, connector, reason):
        self._onConnectionFail(reason)
        ReconnectingClientFactory.clientConnectionFailed(self, connector, reason)


__all__ = ["DivvyClient"]
