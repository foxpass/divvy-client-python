import random
import string

from twisted.internet import reactor
from twisted.internet.endpoints import TCP4ClientEndpoint, connectProtocol
# from twisted.internet.protocol import ClientCreator

from divvy import TwistedDivvyClient
from divvy.protocol import Response

# Ten random IP addresses, to use for rate limiting examples
ip_addresses = ['.'.join([str(random.randrange(256)) for _ in range(4)]) for _ in range(10)]

request_count = 100
response_count = 0


def _cbRateLimit(response, client_ip):
    assert(isinstance(response, Response))
    if response.is_allowed:
        print("{}: allowed, balance is {}".format(client_ip, response.current_credit))
    else:
        print("{}: not allowed, resets in {} seconds".format(client_ip, response.next_reset_seconds))
    global response_count
    response_count += 1
    if response_count == request_count:
        print("*** Stopping reactor, we've handled callbacks for all checks".format(response_count))
        reactor.stop()


def _cbDivvyError(*args, **kwargs):
    print("*** divvyErrorReceived: {}, {}".format(args, kwargs))
    global response_count
    response_count += 1
    if response_count == request_count:
        print("*** Stopping reactor, we've handled callbacks for all checks".format(response_count))
        reactor.stop()


def connectionMade(divvyClient):
    # Get the current working directory
    print("*** Connected to Divvy. Enqueueing {} checks.".format(request_count))
    for i in range(request_count):
        client_ip = random.choice(ip_addresses)
        hit_args = {"method": "GET", "path": "/crisper/carrots", "foo": 3, "ip": client_ip}
        resp = divvyClient.checkRateLimit(**hit_args).addCallback(_cbRateLimit, client_ip).addErrback(_cbDivvyError)


def connectionFailed(f):
    print("*** connectionFailed:")
    print("   f = {}".format(f))


def main():
    point = TCP4ClientEndpoint(reactor, "52.41.9.85", 8321)
    d = connectProtocol(point, TwistedDivvyClient())
    d.addCallbacks(connectionMade, connectionFailed)
    reactor.run()


# this only runs if the module was *not* imported
if __name__ == '__main__':
    main()
