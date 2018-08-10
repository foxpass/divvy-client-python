import time
import threading
from threading import Thread, Timer

from divvy import DivvyClient, Response
from divvy.benchmark import Benchmark


class ThreadedBenchmark(Benchmark):
    def __init__(self, args):
        super(ThreadedBenchmark, self).__init__(args)
        self.reconnect_rate = args.reconnect_rate
        self.thread_count = args.threads
        self.threads = []
        self.timer = None

    def _start(self):
        for _ in range(self.thread_count):
            t = Thread(target=self._run_thread)
            self.threads.append(t)
            t.start()
        if self.time_limit:
            self.timer = Timer(self.time_limit, self.abort)
            self.timer.start()

    def _run(self):
        while True:
            with self.lock:
                count = self.pending_count + self.running_count
                if count <= 0:
                    break
            try:
                time.sleep(0.10)
            except KeyboardInterrupt:
                self.abort()
            self.print_update()

    def _finish(self):
        if self.timer:
            self.timer.cancel()
        for t in self.threads:
            t.join()

    def _print_summary(self):
        self._print_summary_line("Implementation", "Multi-threaded")
        self._print_summary_line("Concurrency level", self.thread_count)
        self._print_summary_line(
            "Auto reconnect rate",
            "N/A" if self.reconnect_rate is None
            else "every {} requests".format(self.reconnect_rate))

    def _run_thread(self):
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
                result = client.check_rate_limit(**self.rate_limit_params())
            except Exception as e:
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
