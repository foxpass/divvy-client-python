from collections import namedtuple

from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.internet.task import deferLater
from twisted.protocols.basic import LineOnlyReceiver
from twisted.protocols.policies import TimeoutMixin

from divvy.exceptions import ServerError
from divvy.protocol import Response, Translator


DeferredRequest = namedtuple("DeferredRequest", ["kwargs", "deferred"])


class DivvyProtocol(LineOnlyReceiver, TimeoutMixin, object):
    # TODO handle timeouts
    # TODO provide a method to close the connection

    delimiter = "\n"

    def __init__(self, encoding='utf-8'):
        super(DivvyProtocol, self).__init__()
        self.queue = []
        self.request_in_transit = None
        self.translator = Translator(encoding)

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
        r = DeferredRequest(kwargs=kwargs, deferred=Deferred())
        self.queue.append(r)
        deferLater(reactor, 0, self._sendNextRequest)
        return r.deferred

    def _sendNextRequest(self):
        if self.request_in_transit is not None:
            # can't send a request while we're waiting on a response for another
            return
        if len(self.queue) == 0:
            # can't send a request if there's nothing enqueued to send
            return

        self.request_in_transit = self.queue.pop(0)
        assert(self.request_in_transit is not None)
        line = self.translator.build_hit(**self.request_in_transit.kwargs)
        self.sendLine(line)

    def lineReceived(self, line):
        # we should never receive a line if we don't have an outstanding request
        assert(self.request_in_transit is not None)

        try:
            response = self.translator.parse_reply(line)
            self.request_in_transit.deferred.callback(response)
        except ServerError as e:
            self.request_in_transit.errback(e)
        finally:
            # Always reset request_in_transit once we received a response
            self.request_in_transit = None

            # If there are more requests in the queue, send the next one
            if len(self.queue) > 0:
                deferLater(reactor, 0, self._sendNextRequest)
