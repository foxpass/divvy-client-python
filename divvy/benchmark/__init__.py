from __future__ import print_function
from collections import namedtuple
import os
import random
import sys
import time
from threading import Lock


Jiffies = namedtuple("Jiffies", ["user", "system"])


class Benchmark(object):
    def __init__(self, args):
        self.host = args.host
        self.port = args.port
        self.timeout = args.socket_timeout
        self.time_limit = args.time_limit

        self.start_time = None
        self.end_time = None

        self.lock = Lock()

        self.desired_count = args.count
        self.pending_count = args.count
        self.running_count = 0
        self.finished_count = 0
        self.error_count = 0
        self.response_times = []

        if args.count > 10:
            self.update_interval = int(round(args.count / 10.0))
            self.next_update = self.update_interval
        else:
            self.update_interval = args.count + 1
            self.next_update = args.count + 1

        # Random IP addresses to use with Divvy's example config.ini

        def _random_ip():
            return '.'.join([str(random.randrange(256)) for _ in range(4)])

        unique_ips = args.count / 10
        self.ip_addresses = [_random_ip() for _ in range(unique_ips)]

    def run(self):
        self.start()
        self._run()
        self.print_update()
        self.finish()

    def abort(self):
        """Ends the benchmark early, by telling the worker threads that there
        aren't any more requests to process."""
        with self.lock:
            self.pending_count = 0

    def get_cpu_jiffies(self):
        """Attempts to use the Linux /proc filesystem to retrieve the amount
        of user and system CPU time consumed. Ignores all errors, for example
        if this isn't running on Linux."""
        try:
            path = "/proc/{}/stat".format(os.getpid())
            with open(path, 'r') as f:
                fields = f.read().strip().split(" ")
                return Jiffies(user=int(fields[13]), system=int(fields[14]))
        except IOError, ValueError:
            return None

    def rate_limit_params(self):
        client_ip = random.choice(self.ip_addresses)
        return {"type": "benchmark", "ip": client_ip}

    def print_update(self):
        """When appropriate, prints a status update for the user."""
        with self.lock:
            f = self.finished_count
            if f >= self.next_update:
                print("Completed {} requests".format(self.next_update))
                self.next_update += self.update_interval

    def print_summary(self):
        """Prints summary data about the entire test."""
        if self.finished_count + self.error_count < 1:
            return
        elapsed_time = self.end_time - self.start_time
        rps = float((self.finished_count + self.error_count) / elapsed_time)
        mean = sum(self.response_times) / float(len(self.response_times))
        ss = sum((x - mean) ** 2 for x in self.response_times)
        stddev = (ss / len(self.response_times)) ** 0.5

        if self.start_jiffies and self.end_jiffies:
            jiffy_hz = os.sysconf(os.sysconf_names['SC_CLK_TCK'])
            jiffies = Jiffies(
                user=self.end_jiffies.user - self.start_jiffies.user,
                system=self.end_jiffies.system - self.start_jiffies.system
            )
            cpu_pct = Jiffies(
                user=float(jiffies.user) / jiffy_hz / elapsed_time * 100.0,
                system=float(jiffies.system) / jiffy_hz / elapsed_time * 100.0
            )
            show_cpu = True
        else:
            show_cpu = False

        print("")
        self._print_summary_line("Server hostname", self.host)
        self._print_summary_line("Server port", self.port)
        self._print_summary()
        self._print_summary_line("Time taken for tests",
                                 "{:.3f} seconds".format(elapsed_time))
        self._print_summary_line("Complete requests", self.finished_count)
        self._print_summary_line("Errors", self.error_count)
        self._print_summary_line("Requests per second",
                                 "{:.3f} per second (mean)".format(rps))
        self._print_summary_line("Time per request",
                                 "{:.3f} ms (mean)".format(mean))
        self._print_summary_line("Standard deviation",
                                 "{:.3f} ms".format(stddev))
        if show_cpu:
            self._print_summary_line("User CPU consumed",
                                     "{:.1f}%".format(cpu_pct.user))
            self._print_summary_line("System CPU consumed",
                                     "{:.1f}%".format(cpu_pct.system))

    def print_histogram(self):
        """Prints data about response times at various percentiles."""
        def _print_percentile(pct, suffix=""):
            pos = int(round((pct / 100.0) * len(self.response_times))) - 1
            time_ms = "{:.3f}".format(self.response_times[pos])
            print("{}%{} ms {}".format(
                str(pct).rjust(3), time_ms.rjust(10), suffix))

        self.response_times.sort()

        print("")
        print("Percentage of requests served within a certain time:")
        _print_percentile(50)
        _print_percentile(66)
        _print_percentile(75)
        _print_percentile(80)
        _print_percentile(90)
        _print_percentile(95)
        _print_percentile(98)
        _print_percentile(99)
        _print_percentile(100, "(longest request)")

    def _print_summary_line(self, key, value):
        print((key + ":").ljust(24) + str(value))

    def start(self):
        """Begins running a benchmark in one or more threads. Subclasses should
        not override this method, but instead implement _start()."""
        self.start_jiffies = self.get_cpu_jiffies()
        self.start_time = time.time()
        self._start()

    def finish(self):
        """Completes execution of the benchmark: Allows all work to finish, and
        prints a summary of results. Subclasses should not override this
        method, but instead implement _finish()."""
        self._finish()
        self.end_time = time.time()
        self.end_jiffies = self.get_cpu_jiffies()
        if self.finished_count + self.error_count > 0:
            self.print_summary()
        if self.finished_count + self.error_count > 1:
            self.print_histogram()

    def _run(self):
        """Subclasses must implement this method, which actually executes the
        benchmark."""
        raise NotImplementedError()

    def _print_summary(self):
        """Subclasses may implement this method to add output to the
        summary."""
        pass

    def _start(self):
        """Subclasses must implement this method, which begins running a
        benchmark."""
        raise NotImplementedError()

    def _finish(self):
        """Subclasses must implement this method, which completes a
        benchmark run."""
        raise NotImplementedError()
