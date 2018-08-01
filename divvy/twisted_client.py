from collections import namedtuple

from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.internet.task import deferLater
from twisted.protocols.basic import LineOnlyReceiver
from twisted.protocols.policies import TimeoutMixin

from divvy.exceptions import ServerError
from divvy.protocol import Response, Translator


DeferredRequest = namedtuple("DeferredRequest", ["kwargs", "deferred"])


#class TwistedDivvyPool(object):
#    def __init__(self, connection_count, encoding='utf-8'):
#        self.clients = [TwistedDivvyClient(encoding) for _ in range(connection_count)]
#
#    def checkRateLimit(self, **kwargs):
#        for client in self.clients:


class TwistedDivvyClient(LineOnlyReceiver, TimeoutMixin, object):
    # TODO handle timeouts
    # TODO provide a method to close the connection

    delimiter = "\n"

    def __init__(self, encoding='utf-8'):
        super(TwistedDivvyClient, self).__init__()
        self.queue = []
        self.request_in_transit = None
        self.translator = Translator(encoding)

    def isReady(self):
        return self.request_in_transit is None

    def checkRateLimit(self, **kwargs):
        d = Deferred()
        r = DeferredRequest(kwargs=kwargs, deferred=d)
        self.queue.append(r)
        deferLater(reactor, 0, self.sendNextHit)
        return d

    def sendNextHit(self):
        if self.request_in_transit is not None:
            # can't send a request while we're waiting on a response for another
            return
        if len(self.queue) == 0:
            # can't send a request if there's nothing enqueued to send
            return
        self.request_in_transit = self.queue.pop(0)
        line = self.translator.build_hit(**self.request_in_transit.kwargs)
        # print("* sending: {}".format(line.strip()))
        self.sendLine(line)

    def lineReceived(self, line):
        # we should never receive a line if we don't have an outstanding request
        assert(self.request_in_transit is not None)
        # print("* received: {}".format(line.strip()))
        try:
            response = self.translator.parse_reply(line)
        except ServerError as e:
            self.request_in_transit.errback(e)
            return
        self.request_in_transit.deferred.callback(response)
        self.request_in_transit = None
        if len(self.queue) > 0:
            deferLater(reactor, 0, self.sendNextHit)
