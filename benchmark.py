from __future__ import print_function
from argparse import ArgumentParser

from divvy.benchmark.twisted_benchmark import TwistedBenchmark
from divvy.benchmark.threaded_benchmark import ThreadedBenchmark


def main():
    desc = "Benchmarks Divvy rate limiter service using divvy-client-python."
    parser = ArgumentParser(description=desc)
    parser.add_argument("host", help="Divvy server hostname")
    parser.add_argument("port", help="Divvy server port", type=int)
    parser.add_argument("--twisted", action="store_true", default=False,
                        help="Use the Twisted implementation")
    parser.add_argument("-n", dest="count", metavar="requests",
                        type=int, default=1000,
                        help="Number of requests to perform")
    parser.add_argument("-c", dest="threads", metavar="concurrency",
                        type=int, default=4,
                        help="Number of multiple requests to make at a time")
    parser.add_argument("-r", dest="reconnect_rate", metavar="conn_reqs",
                        type=int, default=None,
                        help="Cycle each connection after this many requests")
    parser.add_argument("-t", dest="time_limit", metavar="timelimit",
                        type=int, default=None,
                        help="Max seconds to spend on benchmarking")
    parser.add_argument("-s", dest="socket_timeout", metavar="timeout",
                        type=float, default=1.0,
                        help="Max seconds to wait for each response")
    args = parser.parse_args()

    if args.twisted:
        if args.reconnect_rate:
            msg = "Reconnect interval is not supported with --twisted."
            raise Exception(msg)
        if args.threads > 1:
            desc = "{} Twisted connections".format(args.threads)
        else:
            desc = "1 Twisted connection"
    else:
        if args.threads > 1:
            desc = "{} threads".format(args.threads)
        else:
            desc = "1 thread"

    print("Benchmarking {} requests to Divvy at {}:{}, using {}".format(
        args.count, args.host, args.port, desc))

    if args.twisted:
        b = TwistedBenchmark(args)
    else:
        b = ThreadedBenchmark(args)
    b.run()


if __name__ == '__main__':
    main()
