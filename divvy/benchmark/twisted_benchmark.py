import random
import time

from twisted.internet import reactor
from twisted.internet.endpoints import TCP4ClientEndpoint, connectProtocol
from twisted.internet.task import deferLater

from divvy import Response
from divvy.benchmark import Benchmark
from divvy.twisted_client import DivvyClient


class TwistedBenchmark(Benchmark):
    def __init__(self, args):
        super(TwistedBenchmark, self).__init__(args)
        self.connection_count = args.threads
        self.client = DivvyClient(args.host, args.port,
                                  timeout=args.socket_timeout)

    def _start(self):
        for _ in range(self.connection_count):
            self._makeRequest()

        if self.time_limit:
            deferLater(reactor, self.time_limit, self.abort)
        deferLater(reactor, 0.10, self._timer)

    def _run(self):
        # pylint: disable=no-member
        reactor.addSystemEventTrigger("before", "shutdown", self.abort)
        reactor.run()  # pylint: disable=no-member

    def _timer(self):
        self.print_update()
        if reactor._stopped:  # pylint: disable=no-member
            reactor.crash()  # pylint: disable=no-member
        elif self.pending_count + self.running_count > 0:
            deferLater(reactor, 0.10, self._timer)
        else:
            reactor.stop()  # pylint: disable=no-member

    def _makeRequest(self):
        with self.lock:
            assert self.pending_count > 0
            self.pending_count -= 1
            self.running_count += 1
        start_time = time.time()
        d = self.client.check_rate_limit(**self.rate_limit_params())
        d.addBoth(self._handleResponse, start_time=start_time)

    def _handleResponse(self, response, start_time):
        end_time = time.time()
        self.response_times.append((end_time - start_time) * 1000.0)
        success = isinstance(response, Response)
        with self.lock:
            self.running_count -= 1
            if success:
                self.finished_count += 1
            else:
                self.error_count += 1
            make_another = self.pending_count >= 1
        if make_another:
            self._makeRequest()

    def _finish(self):
        if not reactor._stopped:  # pylint: disable=no-member
            reactor.stop()  # pylint: disable=no-member

    def _print_summary(self):
        self._print_summary_line("Implementation", "Twisted")
        self._print_summary_line("Concurrency level", self.connection_count)
