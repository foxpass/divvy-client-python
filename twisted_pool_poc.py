import random
import string

from twisted.internet import reactor
from twisted.internet.address import IPv4Address

from divvy.twisted_pool import DivvyPool

unique_ips = 160
request_count = unique_ips * 5
response_count = 0
connections = 4


def _random_ip():
    return '.'.join([str(random.randrange(256)) for _ in range(4)])


def _cbRateLimit(response, client_ip):
    if response.is_allowed:
        print("{}: allowed, balance is {}".format(
            client_ip, response.current_credit))
    else:
        print("{}: not allowed, resets in {} seconds".format(
            client_ip, response.next_reset_seconds))
    global response_count
    response_count += 1
    if response_count == request_count:
        print("*** Stopping reactor, we've handled callbacks for all checks")
        reactor.stop()  # pylint: disable=no-member


def _cbDivvyError(*args, **kwargs):
    print("*** divvyErrorReceived: {}, {}".format(args, kwargs))
    global response_count
    response_count += 1
    if response_count == request_count:
        print("*** Stopping reactor, we've handled callbacks for all checks")
        reactor.stop()  # pylint: disable=no-member


def connectionFailed(f):
    print("*** connectionFailed:")
    print("   f = {}".format(f))


def main():
    # Ten random IP addresses, to use for rate limiting examples
    ip_addresses = [_random_ip() for _ in range(unique_ips)]

    addr = IPv4Address('TCP', '52.41.9.85', 8321)
    pool = DivvyPool(addr, maxClients=connections)
    print("*** Initialized pool with {} conns; enqueueing {} checks.".format(
        connections, request_count))
    for i in range(request_count):
        client_ip = random.choice(ip_addresses)
        hit_args = {"type": "ldap_login", "ip": client_ip}
        resp = pool.checkRateLimit(**hit_args)
        resp.addCallback(_cbRateLimit, client_ip).addErrback(_cbDivvyError)
    reactor.run()  # pylint: disable=no-member


# this only runs if the module was *not* imported
if __name__ == '__main__':
    main()