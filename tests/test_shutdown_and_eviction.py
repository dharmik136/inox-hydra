"""
Work that was accepted is either done or reported.
==================================================

One place ended something quietly.

  SingleWriterActor.stop() cleared _is_running before sending its sentinel, so
  the worker could leave the loop on its own condition with items still queued.
  The fallback then failed those futures instead of running them. Every item in
  that queue is a SQLite write a caller submitted and is blocked on, so a
  graceful shutdown silently discarded writes. Its drain also caught Exception
  and broke, so one bad item left every future behind it unresolved and its
  caller waiting on .result() forever.

The companion case, an EventBus subscriber evicted and left blocked, went with
the bus itself in cycle 3: it had seven publishers and no subscriber anywhere,
and the routes that served it were removed in cycle 2.
"""

import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from studio.core.rate_limiter import SingleWriterActor


def test_a_graceful_stop_executes_the_writes_it_was_given():
    """
    The defining case. Submit work, stop immediately, and every write must
    have happened. These are database writes, not best effort notifications.
    """
    actor = SingleWriterActor()
    done = []
    gate = threading.Event()

    # Occupy the worker so the rest of the batch is still queued at stop().
    actor.submit(gate.wait)
    futures = [actor.submit(done.append, index) for index in range(25)]

    gate.set()
    actor.stop(timeout=5.0)

    assert len(done) == 25, (
        f"only {len(done)} of 25 queued writes ran before shutdown, so the "
        f"rest were discarded while their callers were told the actor stopped "
        f"cleanly"
    )
    assert sorted(done) == list(range(25))
    for future in futures:
        assert future.done(), "a caller is still blocked on a write that will never run"
        assert future.exception() is None


def test_one_failing_write_does_not_strand_the_ones_behind_it():
    """
    The drain caught Exception and broke out of the loop, so everything after
    the failure kept an unresolved future and its caller blocked forever.
    """
    actor = SingleWriterActor()
    gate = threading.Event()

    def explode():
        raise ValueError("this write fails")

    actor.submit(gate.wait)
    bad = actor.submit(explode)
    after = [actor.submit(lambda n=n: n) for n in range(10)]

    gate.set()
    actor.stop(timeout=5.0)

    assert isinstance(bad.exception(), ValueError)
    for index, future in enumerate(after):
        assert future.done(), (
            f"future {index} was never resolved, because one failure ended the "
            f"drain and left its caller waiting on .result() with no timeout"
        )


def test_stopping_twice_is_harmless():
    actor = SingleWriterActor()
    actor.stop(timeout=2.0)
    actor.stop(timeout=2.0)
    with pytest.raises(RuntimeError):
        actor.submit(lambda: None)
