"""
Thread-safe sliding-window rate limiter, shared across every OpenAI call in
the app (explain_flags.py and fuzzy_match.py both import the same instance).

Even on a paid tier, OpenAI enforces a requests-per-minute cap based on your
usage tier. Parallel calls firing all at once could still exceed it on a
larger dataset. This limiter makes excess calls WAIT for a free slot instead
of firing and risking a 429 - calls still run in parallel up to the quota,
beyond that they queue in the order they arrived rather than getting rejected.
"""
import time
import threading
from collections import deque

import config


class RateLimiter:
    def __init__(self, max_calls_per_minute):
        self.max_calls = max_calls_per_minute
        self.window_seconds = 60
        self.call_times = deque()
        self.lock = threading.Lock()

    def acquire(self):
        """Blocks until a call slot is available, then reserves it."""
        while True:
            with self.lock:
                now = time.time()
                # Drop timestamps older than the sliding window
                while self.call_times and now - self.call_times[0] > self.window_seconds:
                    self.call_times.popleft()

                if len(self.call_times) < self.max_calls:
                    self.call_times.append(now)
                    return

                # Window is full - figure out exactly how long until the oldest call ages out
                wait_time = self.window_seconds - (now - self.call_times[0]) + 0.1

            time.sleep(max(wait_time, 0.1))


# Shared across the whole app.
llm_limiter = RateLimiter(max_calls_per_minute=config.OPENAI_RPM_LIMIT)
