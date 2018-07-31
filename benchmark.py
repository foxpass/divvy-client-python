# coding: utf-8

from __future__ import print_function
from argparse import ArgumentParser
from collections import namedtuple
import math
import os
import random
import sys
import time
import threading
from threading import Lock, Thread, Timer

from divvy import DivvyClient, Response


Jiffies = namedtuple("Jiffies", ["user", "system"])


class Benchmark(object):
    def __init__(self, args):
        self.host = args.host
        self.port = args.port
        self.timeout = args.socket_timeout
        self.time_limit = args.time_limit
        self.thread_count = args.threads
        self.reconnect_rate = args.reconnect_rate

        self.start_time = None
        self.end_time = None
        self.timer = None

        self.threads = []
        self.lock = Lock()

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

    def start(self):
        """Begins running a benchmark in one or more threads."""
        self.start_jiffies = self.get_cpu_jiffies()
        self.start_time = time.time()
        for _ in range(self.thread_count):
            t = Thread(target=self.run_thread)
            self.threads.append(t)
            t.start()
        if self.time_limit:
            self.timer = Timer(self.time_limit, self.abort)
            self.timer.start()

    def run_thread(self):
        """Execute the benchmark in a single thread. Coordinates with other
        threads, if any exist, so that the correct number of requests are
        issued."""
        client = DivvyClient(self.host, self.port, socket_timeout=self.timeout)
        conn_requests = 0
        while True:
            with self.lock:
                if self.pending_count <= 0:
                    break
                self.pending_count -= 1
                self.running_count += 1
            start_time = time.time()
            success = True
            try:
                result = client.hit(method="GET", path="/status")
            except Exception:
                success = False
            end_time = time.time()
            if success:
                success = isinstance(result, Response)
            conn_requests += 1
            with self.lock:
                self.running_count -= 1
                if success:
                    self.finished_count += 1
                else:
                    self.error_count += 1
                self.response_times.append((end_time - start_time) * 1000.0)
            if self.reconnect_rate and conn_requests > self.reconnect_rate:
                client.connection.disconnect()
                client = DivvyClient(self.host, self.port,
                                     socket_timeout=self.timeout)
        client.connection.disconnect()

    def abort(self):
        """Ends the benchmark early, by telling the worker threads that there
        aren't any more requests to process."""
        with self.lock:
            self.pending_count = 0

    def finish(self):
        """Completes execution of the benchmark: Allows all other threads to
        finish, and prints a summary of results."""
        if self.timer:
            self.timer.cancel()
        for t in self.threads:
            t.join()
        self.end_time = time.time()
        self.end_jiffies = self.get_cpu_jiffies()
        self.print_results()

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

    def print_update(self):
        """When appropriate, prints a status update for the user."""
        with self.lock:
            f = self.finished_count
            if f >= self.next_update:
                print("Completed {} requests".format(self.next_update))
                self.next_update += self.update_interval

    def print_results(self):
        if self.finished_count + self.error_count > 0:
            self.print_summary()
        if self.finished_count + self.error_count > 1:
            self.print_histogram()

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

        def _print_summary_line(key, value):
            print((key + ":").ljust(24) + str(value))

        print("")
        _print_summary_line("Server hostname", self.host)
        _print_summary_line("Server port", self.port)
        _print_summary_line("Concurrency level", self.thread_count)
        _print_summary_line(
            "Auto reconnect rate",
            "N/A" if self.reconnect_rate is None
            else "every {} requests".format(self.reconnect_rate))
        _print_summary_line("Time taken for tests",
                            "{:.3f} seconds".format(elapsed_time))
        _print_summary_line("Complete requests", self.finished_count)
        _print_summary_line("Errors", self.error_count)
        _print_summary_line("Requests per second",
                            "{:.3f} per second (mean)".format(rps))
        _print_summary_line("Time per request",
                            "{:.3f} ms (mean)".format(mean))
        _print_summary_line("Standard deviation",
                            "{:.3f} ms".format(stddev))
        if show_cpu:
            _print_summary_line("User CPU consumed",
                                "{:.1f}%".format(cpu_pct.user))
            _print_summary_line("System CPU consumed",
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


def main():
    desc = "Benchmarks Divvy rate limiter service using divvy-client-python."
    parser = ArgumentParser(description=desc)
    parser.add_argument("host", help="Divvy server hostname")
    parser.add_argument("port", help="Divvy server port", type=int)
    parser.add_argument("-n", dest="count", metavar="requests",
                        type=int, default=1000,
                        help="Number of requests to perform")
    parser.add_argument("-c", dest="threads", metavar="concurrency",
                        type=int, default=4,
                        help="Number of multiple requests to make at a time")
    parser.add_argument("-r", dest="reconnect_rate", metavar="requests",
                        type=int, default=None,
                        help="Cycle each connection after this many requests")
    parser.add_argument("-t", dest="time_limit", metavar="timelimit",
                        type=int, default=None,
                        help="Max seconds to spend on benchmarking")
    parser.add_argument("-s", dest="socket_timeout", metavar="timeout",
                        type=float, default=1.0,
                        help="Max seconds to wait for each response")
    args = parser.parse_args()
    print("Benchmarking {} requests to Divvy at {}:{}, using {} {}".format(
        args.count, args.host, args.port, args.threads,
        "threads" if args.threads > 1 else "thread"))

    b = Benchmark(args)
    b.start()

    while threading.active_count() > (2 if args.time_limit else 1):
        try:
            time.sleep(0.1)
        except KeyboardInterrupt:
            b.abort()
        b.print_update()

    b.print_update()
    b.finish()


if __name__ == '__main__':
    main()
