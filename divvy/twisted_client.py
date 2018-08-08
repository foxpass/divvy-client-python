from collections import namedtuple

from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.internet.error import TimeoutError
from twisted.internet.task import deferLater
from twisted.protocols.basic import LineOnlyReceiver
from twisted.protocols.policies import TimeoutMixin

from divvy.exceptions import ServerError
from divvy.protocol import Response, Translator


DeferredRequest = namedtuple("DeferredRequest", ["kwargs", "deferred"])


class DivvyProtocol(LineOnlyReceiver, TimeoutMixin, object):
    delimiter = "\n"

    def __init__(self, timeout=1.0, encoding='utf-8'):
        super(DivvyProtocol, self).__init__()
        self.request = None
        self.timeout = timeout
        self.translator = Translator(encoding)

    def timeoutConnection(self):
        TimeoutMixin.timeoutConnection(self)
        # self.request should be present whenever this method is called, but
        # let's program defensively and double-check.
        if self.request:
            self.request.deferred.errback(TimeoutError())

    def checkRateLimit(self, **kwargs):
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
        self.request = DeferredRequest(kwargs=kwargs, deferred=Deferred())
        line = self.translator.build_hit(**self.request.kwargs)
        self.sendLine(line)
        self.setTimeout(self.timeout)

        return self.request.deferred

    def lineReceived(self, line):
        self.setTimeout(None)

        assert self.request

        # we're now able to server another caller, so store
        # the request before clearing it. once we call the callbacks
        # another client might grab this object before we're done with it
        request = self.request

        self.request = None

        try:
            response = self.translator.parse_reply(line)
            request.deferred.callback(response)
        except Exception as e:
            request.deferred.errback(e)

