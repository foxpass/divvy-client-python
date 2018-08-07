import time

from twisted.internet import reactor
from twisted.internet.address import HostnameAddress
from twisted.internet.task import deferLater

from divvy import Response
from divvy.benchmark import Benchmark
from divvy.twisted_pool import DivvyPool


class TwistedBenchmark(Benchmark):
    def __init__(self, args):
        super(TwistedBenchmark, self).__init__(args)
        self.connection_count = args.threads

    def _start(self):
        addr = HostnameAddress(self.host, self.port)
        self.pool = DivvyPool(addr, maxClients=self.connection_count)

        if self.time_limit:
            deferLater(reactor, self.time_limit, self.abort)
        for i in range(self.connection_count):
            d = self.pool.checkRateLimit(**self.rate_limit_params())
            d.addBoth(self._cbRateLimit, start_time=time.time())
            with self.lock:
                self.pending_count -= 1
                self.running_count += 1
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

    def _cbRateLimit(self, result, start_time):
        end_time = time.time()
        success = isinstance(result, Response)
        with self.lock:
            self.running_count -= 1
            if success:
                self.finished_count += 1
            else:
                self.error_count += 1
            self.response_times.append((end_time - start_time) * 1000.0)
            if self.pending_count >= 1:
                d = self.pool.checkRateLimit(_method="GET", path="/status")
                d.addBoth(self._cbRateLimit, start_time=time.time())
                self.pending_count -= 1
                self.running_count += 1

    def _finish(self):
        if not reactor._stopped:  # pylint: disable=no-member
            reactor.stop()  # pylint: disable=no-member

    def _print_summary(self):
        self._print_summary_line("Implementation", "Twisted")
        self._print_summary_line("Concurrency level", self.connection_count)
