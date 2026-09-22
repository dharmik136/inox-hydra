"""
Gaussian Jittered Token Bucket Rate Limiter & Single-Writer Concurrency Actor.
==============================================================================
Implements anti-bot detection safeguards from Project Prudent PRD-002:
- Statistical pacing: Delta t = mu + sigma * N(0, 1)
- Mean interval mu = 900.0 seconds (15 minutes).
- Standard deviation sigma = 120.0 seconds (2 minutes).
- Clamping bounds: [mu - 2*sigma, mu + 2*sigma] = [660.0s, 1140.0s].
- Single-Writer Actor Queue to serialize writes under SQLite WAL mode.

Strict Invariants:
- Zero em-dashes across all code, docstrings, and comments.
- 100% deterministic clamping guarantees.
"""

from concurrent.futures import Future
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Tuple
import logging
import queue
import random
import threading
import time

logger = logging.getLogger("studio.rate_limiter")


def generate_gaussian_interval(
    mu: float = 900.0,
    sigma: float = 120.0,
    clamp_sigmas: float = 2.0
) -> float:
    """
    Generates a Gaussian (normally distributed) interval with strict clamping bounds.
    Equation: Delta t = mu + sigma * N(0, 1)
    Clamping: Delta t in [mu - clamp_sigmas * sigma, mu + clamp_sigmas * sigma]
    Default: [900 - 240, 900 + 240] = [660.0s, 1140.0s] (11 to 19 minutes).
    """
    safe_mu = max(0.001, float(mu))
    safe_sigma = max(0.0, float(sigma))
    safe_sigmas = max(0.0, float(clamp_sigmas))

    min_bound = max(0.001, safe_mu - (safe_sigmas * safe_sigma))
    max_bound = safe_mu + (safe_sigmas * safe_sigma)
    raw_sample = random.gauss(safe_mu, safe_sigma)
    clamped_sample = max(min_bound, min(max_bound, raw_sample))
    return round(clamped_sample, 3)


class GaussianRateLimiter:
    """
    Token bucket rate limiter governed by Gaussian jitter to eliminate periodic timing footprints.
    Guarantees internal polling and verification calls adhere to human entropy distributions.
    """

    def __init__(
        self,
        mu: float = 900.0,
        sigma: float = 120.0,
        clamp_sigmas: float = 2.0,
        capacity: float = 1.0,
        initial_tokens: Optional[float] = None,
    ):
        self.mu = max(0.001, float(mu))
        self.sigma = max(0.0, float(sigma))
        self.clamp_sigmas = max(0.0, float(clamp_sigmas))
        self.capacity = max(0.01, float(capacity))
        self.refill_rate = 1.0 / self.mu  # Tokens per second
        init_t = self.capacity if initial_tokens is None else float(initial_tokens)
        self._tokens = max(0.0, min(self.capacity, init_t))
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()
        self.total_acquisitions = 0
        self.total_rejections = 0
        self.last_acquired_at: Optional[str] = None

    @property
    def min_bound(self) -> float:
        return max(0.001, self.mu - (self.clamp_sigmas * self.sigma))

    @property
    def max_bound(self) -> float:
        return self.mu + (self.clamp_sigmas * self.sigma)

    def _refill(self):
        """Internal helper to replenish tokens according to elapsed monotonic time."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        if elapsed > 0:
            self._tokens = min(self.capacity, self._tokens + (elapsed * self.refill_rate))
            self._last_refill = now

    def calculate_next_interval(self) -> float:
        """Returns the next Gaussian-jittered interval in seconds."""
        return generate_gaussian_interval(self.mu, self.sigma, self.clamp_sigmas)

    def consume(self, tokens: float = 1.0) -> bool:
        """
        Non-blocking token consumption check.
        Returns True if tokens were available and consumed, False otherwise.
        """
        try:
            tok = float(tokens)
        except (TypeError, ValueError):
            tok = 1.0

        if tok <= 0.0:
            return True

        with self._lock:
            self._refill()
            if self._tokens >= tok:
                self._tokens -= tok
                self.total_acquisitions += 1
                self.last_acquired_at = datetime.now(timezone.utc).isoformat()
                return True
            self.total_rejections += 1
            return False

    def wait_time_seconds(self, tokens: float = 1.0) -> float:
        """
        Calculates how many seconds caller must wait before tokens are available.
        If tokens are available immediately, returns 0.0.
        If unavailable, returns a Gaussian-jittered wait interval.
        """
        try:
            tok = float(tokens)
        except (TypeError, ValueError):
            tok = 1.0

        if tok <= 0.0:
            return 0.0

        with self._lock:
            self._refill()
            if self._tokens >= tok:
                return 0.0
            # Token bucket empty: apply Gaussian-jittered wait
            return self.calculate_next_interval()

    def acquire(self, tokens: float = 1.0, block: bool = True, timeout: Optional[float] = None) -> bool:
        """
        Acquires tokens, optionally blocking until the Gaussian wait interval elapses.
        Thread-safe across concurrent callers.
        """
        try:
            tok = float(tokens)
        except (TypeError, ValueError):
            tok = 1.0

        if tok <= 0.0:
            return True

        parsed_timeout: Optional[float] = None
        if timeout is not None:
            try:
                parsed_timeout = max(0.0, float(timeout))
            except (TypeError, ValueError):
                parsed_timeout = None

        start_time = time.monotonic()
        while True:
            with self._lock:
                self._refill()
                if self._tokens >= tok:
                    self._tokens -= tok
                    self.total_acquisitions += 1
                    self.last_acquired_at = datetime.now(timezone.utc).isoformat()
                    return True

            if not block:
                self.total_rejections += 1
                return False

            if parsed_timeout is not None and parsed_timeout <= 0.0:
                self.total_rejections += 1
                return False

            sleep_duration = min(self.calculate_next_interval(), 0.5)
            if parsed_timeout is not None:
                elapsed = time.monotonic() - start_time
                if elapsed + sleep_duration > parsed_timeout:
                    remaining = parsed_timeout - elapsed
                    if remaining > 0:
                        time.sleep(remaining)
                    self.total_rejections += 1
                    return False

            time.sleep(sleep_duration)

    def reset(self, tokens: Optional[float] = None):
        """Resets the token bucket to full capacity."""
        with self._lock:
            if tokens is None:
                self._tokens = self.capacity
            else:
                try:
                    self._tokens = max(0.0, min(self.capacity, float(tokens)))
                except (TypeError, ValueError):
                    self._tokens = self.capacity
            self._last_refill = time.monotonic()

    def get_diagnostics(self) -> Dict[str, Any]:
        """Telemetry diagnostics for the rate limiter."""
        with self._lock:
            self._refill()
            available = round(self._tokens, 3)
            return {
                "capacity": self.capacity,
                "available_tokens": available,
                "refill_rate_per_sec": round(self.refill_rate, 6),
                "mean_interval_seconds": self.mu,
                "std_deviation_seconds": self.sigma,
                "clamping_bounds": [self.min_bound, self.max_bound],
                "sample_next_interval": self.calculate_next_interval(),
                "total_acquisitions": self.total_acquisitions,
                "total_rejections": self.total_rejections,
                "last_acquired_at": self.last_acquired_at,
            }


class SingleWriterActor:
    """
    Centralized Single-Writer Actor Queue for SQLite WAL Concurrency.
    Serializes all write tasks to guarantee zero 'database is locked' errors.
    """

    def __init__(self, maxsize: int = 2000):
        self._queue: queue.Queue = queue.Queue(maxsize=maxsize)
        self._is_running = True
        self.total_tasks_processed = 0
        self.total_errors = 0
        self._worker_thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="SingleWriterActorThread"
        )
        self._worker_thread.start()

    def _run_loop(self):
        """Processes serialized write callables continuously."""
        while self._is_running:
            try:
                item = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if item is None:
                # The stop sentinel. Anything queued before it was accepted by
                # submit() and is a database write the caller is waiting on, so
                # it is executed rather than abandoned. Stopping is not a
                # reason to lose work that was already promised.
                self._drain_remaining()
                break

            func, args, kwargs, future = item
            try:
                result = func(*args, **kwargs)
                future.set_result(result)
                self.total_tasks_processed += 1
            except Exception as exc:
                self.total_errors += 1
                logger.error(f"SingleWriterActor task execution error: {exc}")
                future.set_exception(exc)
            finally:
                self._queue.task_done()

    def submit(self, func: Callable, *args, **kwargs) -> Future:
        """Submits a write task asynchronously, returning a concurrent Future."""
        if not callable(func):
            raise TypeError("Task target func must be callable.")
        if not self._is_running:
            raise RuntimeError("SingleWriterActor is shut down.")
        future = Future()
        try:
            self._queue.put((func, args, kwargs, future), timeout=5.0)
        except queue.Full:
            raise RuntimeError("SingleWriterActor queue is full.")
        return future

    def execute_sync(self, func: Callable, *args, timeout: float = 10.0, **kwargs) -> Any:
        """Executes a write task synchronously through the serialized queue."""
        if not callable(func):
            raise TypeError("Task target func must be callable.")
        future = self.submit(func, *args, **kwargs)
        return future.result(timeout=timeout)

    def _drain_remaining(self):
        """Executes everything still queued. Called by the worker on shutdown."""
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                return
            if item is None:
                self._queue.task_done()
                continue
            func, args, kwargs, future = item
            try:
                if not future.done():
                    future.set_result(func(*args, **kwargs))
                    self.total_tasks_processed += 1
            except Exception as exc:
                self.total_errors += 1
                logger.error(f"SingleWriterActor drain error: {exc}")
                if not future.done():
                    future.set_exception(exc)
            finally:
                self._queue.task_done()

    def stop(self, timeout: float = 3.0):
        """
        Halts the actor, executing whatever was already queued.

        The order matters. _is_running was cleared before the sentinel was
        sent, so the loop could exit on its own condition with items still in
        the queue, and the fallback below then failed those futures rather
        than running them. Every one of them is a SQLite write a caller
        submitted and is waiting on, so a graceful stop was silently
        discarding writes.

        The sentinel goes first and the flag is cleared after, so the worker
        reaches the sentinel, drains what is left, and exits.
        """
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass

        if self._worker_thread.is_alive():
            self._worker_thread.join(timeout=timeout)

        self._is_running = False

        # Anything still here means the worker did not finish within the
        # timeout. Those callers are told, rather than left waiting forever.
        #
        # One failure no longer ends the loop: the old handler caught
        # Exception and broke, so a single problem item left every future
        # behind it unresolved and its caller blocked on .result().
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            except Exception:
                break
            try:
                if item is not None:
                    _, _, _, future = item
                    if not future.done():
                        future.set_exception(
                            RuntimeError("SingleWriterActor shut down before task execution.")
                        )
            except Exception as exc:
                logger.error(f"SingleWriterActor shutdown notification error: {exc}")
            finally:
                try:
                    self._queue.task_done()
                except Exception:
                    pass

    def get_metrics(self) -> Dict[str, Any]:
        """Telemetry diagnostics for the single-writer queue."""
        return {
            "queue_depth": self._queue.qsize(),
            "tasks_processed": self.total_tasks_processed,
            "errors": self.total_errors,
            "is_alive": self._worker_thread.is_alive(),
        }


# Global Singletons
rate_limiter = GaussianRateLimiter(mu=900.0, sigma=120.0, clamp_sigmas=2.0)
write_actor = SingleWriterActor()
