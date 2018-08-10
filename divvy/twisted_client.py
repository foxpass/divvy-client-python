from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.internet.endpoints import TCP4ClientEndpoint, connectProtocol
from twisted.internet.error import TimeoutError
from twisted.internet.task import deferLater
from twisted.python.failure import Failure
from twisted.protocols.basic import LineOnlyReceiver
from twisted.protocols.policies import TimeoutMixin

from divvy.protocol import Translator


class DivvyClient(object):
    def __init__(self, host, port, timeout=1.0, encoding='utf-8'):
        """
        Configures a client that can speak to a Divvy rate limiting server.
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.encoding = encoding

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
        request = DivvyRequest(self.host, self.port, self.timeout,
                               self.encoding, hit_args)
        return request.deferred


class DivvyRequest(object):
    """
    Represents a single connection which handles a single request to a Divvy
    server. You shouldn't need to use this in client code.
    """

    def __init__(self, host, port, timeout, encoding, hit_args):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.encoding = encoding
        self.hit_args = hit_args

        endpoint = TCP4ClientEndpoint(reactor, self.host, self.port,
                                      self.timeout)
        self.deferred = Deferred()
        protocol = DivvyProtocol(timeout=self.timeout, encoding=self.encoding)
        d = connectProtocol(endpoint, protocol)
        d.addCallbacks(self._handleConnection, self.deferred.errback)

    def _handleConnection(self, protocol):
        # Once connected, issue the HIT over the wire, and have the response
        # sent directly to the forehead.
        #
        # Errr, to the Deferred object that your client code will be accessing.
        return protocol.checkRateLimit(**self.hit_args).chainDeferred(
            self.deferred)


class DivvyProtocol(LineOnlyReceiver, TimeoutMixin, object):
    """
    Twisted handler for network communication with a Divvy server.
    """

    delimiter = "\n"

    def __init__(self, timeout=1.0, encoding='utf-8'):
        super(DivvyProtocol, self).__init__()
        self.timeout = timeout
        self.translator = Translator(encoding)
        self.deferred = None

    def timeoutConnection(self):
        TimeoutMixin.timeoutConnection(self)
        # self.deferred should be present whenever this method is
        # called, but let's program defensively and double-check.
        if self.deferred:
            self.deferred.errback(TimeoutError())

    def checkRateLimit(self, **kwargs):
        assert self.connected
        assert self.deferred is None
        self.deferred = Deferred()
        line = self.translator.build_hit(**kwargs).strip()
        self.sendLine(line)
        self.setTimeout(self.timeout)

        return self.deferred

    def lineReceived(self, line):
        self.setTimeout(None)

        # we should never receive a line if there's no outstanding request
        assert self.deferred is not None

        try:
            response = self.translator.parse_reply(line)
            self.deferred.callback(response)
        except Exception as e:
            self.deferred.errback(e)
        finally:
            self.transport.loseConnection()
            self.deferred = None


__all__ = ["DivvyClient"]
