from argparse import ArgumentParser
import random
import string

from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.internet.endpoints import TCP4ClientEndpoint, connectProtocol
from twisted.internet.task import deferLater
from twisted.python.failure import Failure

from divvy import Response as DivvyResponse
from divvy.twisted_client import DivvyClient

unique_ips = 5
request_count = unique_ips * 5
response_count = 0
connections = 4
divvy_client = None


def main():
    parser = ArgumentParser()
    parser.add_argument("hostname", type=str, help="Divvy server host")
    parser.add_argument("port", nargs="?", default="8321", type=int,
                        help="Divvy server port (default is 8321)")
    args = parser.parse_args()

    global divvy_client
    divvy_client = DivvyClient(args.hostname, args.port)
    deferLater(reactor, 0, do_example)
    reactor.run()  # pylint: disable=no-member


def _random_ip():
    return '.'.join([str(random.randrange(256)) for _ in range(4)])


# Client code -- this is similar to what would go in ldapserver's bind.py
# (or maybe )
def do_example():
    # Random IP addresses, to use for rate limiting examples
    ip_addresses = [_random_ip() for _ in range(unique_ips)]

    # Pretend like we got a bunch of login requests...
    print("*** Enqueueing {} checks.".format(
        request_count))
    for i in range(request_count):
        client_ip = random.choice(ip_addresses)
        hit_args = {'type': 'benchmark', 'ip': client_ip}
        d = divvy_client.check_rate_limit(**hit_args)
        d.addErrback(fail_open, client_ip=client_ip)
        d.addCallback(continue_login, client_ip=client_ip)


def continue_login(response, client_ip):
    if response.is_allowed:
        print("{}: allowed, balance is {}".format(
            client_ip, response.current_credit))
    else:
        print("{}: not allowed, will reset in {} seconds".format(
            client_ip, response.next_reset_seconds))

    global response_count
    response_count += 1
    if response_count == request_count:
        print("*** Stopping reactor, we've handled callbacks for all checks")
        reactor.stop()  # pylint: disable=no-member


def fail_open(reason, client_ip):
    assert(isinstance(reason, Failure))
    # TODO record the failure in server logs
    print("{}: request failed, let the user through anyway".format(client_ip))
    return DivvyResponse(True, 0, 0)


# And this is what goes in rate_limits.py


if __name__ == '__main__':
    main()
