"""
Work that was accepted is either done or reported.
==================================================

Two places ended something quietly.

  SingleWriterActor.stop() cleared _is_running before sending its sentinel, so
  the worker could leave the loop on its own condition with items still queued.
  The fallback then failed those futures instead of running them. Every item in
  that queue is a SQLite write a caller submitted and is blocked on, so a
  graceful shutdown silently discarded writes. Its drain also caught Exception
  and broke, so one bad item left every future behind it unresolved and its
  caller waiting on .result() forever.

  EventBus evicted the oldest subscriber by removing its queue from the list.
  The queue was gone but the generator was still blocked on queue.get(), and
  nothing would ever write to it again. To the browser that is not an error and
  not a close, just a stream that went quiet, so EventSource never reconnects.
  The dashboard stops updating and says nothing.
"""

import asyncio
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "studio", "backend")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import event_bus as event_bus_module
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


async def _drain(generator, sink=None):
    async for event in generator:
        if sink is not None:
            sink.append(event)


async def _settle():
    for _ in range(30):
        await asyncio.sleep(0)


async def _park(bus, count):
    """
    Starts `count` subscribers and lets each reach its queue.

    subscribe() is an async generator, so nothing registers until the first
    __anext__. A test that only calls subscribe() therefore proves nothing,
    which is worth saying out loud because it is the easy way to write this
    test wrong.
    """
    tasks = [asyncio.create_task(_drain(bus.subscribe())) for _ in range(count)]
    await _settle()
    return tasks


def test_an_evicted_subscriber_is_woken_rather_than_left_blocked():
    """
    Removing the queue stops delivery. It does not stop the generator waiting
    on it. Ending the generator is what closes the response and lets the
    browser reconnect.
    """
    async def scenario():
        bus = event_bus_module.EventBus()
        received = []
        first = asyncio.create_task(_drain(bus.subscribe(), received))
        await _settle()
        assert len(bus._subscribers) == 1, "the first subscriber never registered"

        await _park(bus, event_bus_module.MAX_SUBSCRIBERS)

        await asyncio.wait_for(first, timeout=3.0)
        return received

    received = asyncio.run(scenario())
    assert not any(item is event_bus_module._EVICTED for item in received), (
        "the eviction sentinel was handed to the client as if it were an event"
    )


def test_an_evicted_subscriber_is_woken_even_when_its_queue_is_full():
    """
    The backed up client is the one most likely to be evicted, so a full queue
    is the ordinary case here rather than the exotic one.
    """
    async def scenario():
        bus = event_bus_module.EventBus()
        first = asyncio.create_task(_drain(bus.subscribe()))
        await _settle()

        queue = bus._subscribers[0]
        while not queue.full():
            queue.put_nowait({"type": "filler", "id": 0})

        await _park(bus, event_bus_module.MAX_SUBSCRIBERS)
        await asyncio.wait_for(first, timeout=5.0)

    asyncio.run(scenario())


def test_eviction_still_bounds_the_subscriber_list():
    """The wake up must not have cost the memory bound it exists to enforce."""
    async def scenario():
        bus = event_bus_module.EventBus()
        await _park(bus, event_bus_module.MAX_SUBSCRIBERS + 20)
        return len(bus._subscribers)

    assert asyncio.run(scenario()) <= event_bus_module.MAX_SUBSCRIBERS


def test_a_live_subscriber_still_receives_events():
    """Guard against the sentinel path ending healthy streams."""
    async def scenario():
        bus = event_bus_module.EventBus()
        received = []

        async def consume(generator):
            async for event in generator:
                received.append(event)
                break

        task = asyncio.create_task(consume(bus.subscribe()))
        await _settle()
        await bus.publish("probe", {"ok": True})
        await asyncio.wait_for(task, timeout=3.0)
        return received

    received = asyncio.run(scenario())
    assert received and received[0].get("event") == "probe"
