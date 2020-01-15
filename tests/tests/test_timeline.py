# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

import collections
import functools
import itertools
import pytest
import threading
import time

from debugpy.common import log, messaging
from tests.patterns import some
from tests.timeline import Timeline, Mark, Event, Request, Response


class MessageFactory(object):
    """A factory for DAP messages that are not bound to a message channel.
    """

    def __init__(self):
        self._seq_iter = itertools.count(1)
        self.messages = collections.OrderedDict()
        self.event = functools.partial(self._make, messaging.Event)
        self.request = functools.partial(self._make, messaging.Request)
        self.response = functools.partial(self._make, messaging.Response)

    def _make(self, message_type, *args, **kwargs):
        message = message_type(None, next(self._seq_iter), *args, **kwargs)
        self.messages[message.seq] = message
        return message


@pytest.fixture
def make_timeline(request):
    """Provides a timeline factory. All timelines created by this factory
    are automatically finalized and checked for basic consistency after the
    end of the test.
    """

    timelines = []

    def factory():
        timeline = Timeline()
        timelines.append(timeline)
        with timeline.frozen():
            assert timeline.beginning is not None
            initial_history = [some.object.same_as(timeline.beginning)]
            assert timeline.history() == initial_history
        return timeline, initial_history

    yield factory
    log.newline()

    try:
        failed = request.node.call_result.failed
    except AttributeError:
        pass
    else:
        if not failed:
            for timeline in timelines:
                timeline.finalize()
                history = timeline.history()
                history.sort(key=lambda occ: occ.timestamp)
                assert history == timeline.history()
                assert history[-1] == Mark("FINISH")
                timeline.close()


@pytest.mark.timeout(1)
def test_occurrences(make_timeline):
    timeline, initial_history = make_timeline()

    mark1 = timeline.mark("dum")
    mark2 = timeline.mark("dee")
    mark3 = timeline.mark("dum")

    assert mark1 == Mark("dum")
    assert mark1.id == "dum"
    assert mark2 == Mark("dee")
    assert mark2.id == "dee"
    assert mark3 == Mark("dum")
    assert mark3.id == "dum"

    with timeline.frozen():
        assert timeline.history() == initial_history + [
            some.object.same_as(mark1),
            some.object.same_as(mark2),
            some.object.same_as(mark3),
        ]
        timeline.finalize()

    assert timeline.all_occurrences_of(Mark("dum")) == (
        some.object.same_as(mark1),
        some.object.same_as(mark3),
    )
    assert timeline.all_occurrences_of(Mark("dee")) == (some.object.same_as(mark2),)

    assert timeline[:].all_occurrences_of(Mark("dum")) == (
        some.object.same_as(mark1),
        some.object.same_as(mark3),
    )

    # Lower boundary is inclusive.
    assert timeline[mark1:].all_occurrences_of(Mark("dum")) == (
        some.object.same_as(mark1),
        some.object.same_as(mark3),
    )
    assert timeline[mark2:].all_occurrences_of(Mark("dum")) == (
        some.object.same_as(mark3),
    )
    assert timeline[mark3:].all_occurrences_of(Mark("dum")) == (
        some.object.same_as(mark3),
    )

    # Upper boundary is exclusive.
    assert timeline[:mark1].all_occurrences_of(Mark("dum")) == ()
    assert timeline[:mark2].all_occurrences_of(Mark("dum")) == (
        some.object.same_as(mark1),
    )
    assert timeline[:mark3].all_occurrences_of(Mark("dum")) == (
        some.object.same_as(mark1),
    )


def expectation_of(message):
    if isinstance(message, messaging.Event):
        return Event(some.str.equal_to(message.event), some.dict.equal_to(message.body))
    elif isinstance(message, messaging.Request):
        return Request(
            some.str.equal_to(message.command), some.dict.equal_to(message.arguments)
        )
    else:
        raise AssertionError("Unsupported message type")


def test_event(make_timeline):
    timeline, initial_history = make_timeline()
    messages = MessageFactory()

    event_msg = messages.event("stopped", {"reason": "pause"})
    event_exp = expectation_of(event_msg)
    event = timeline.record_event(event_msg)

    assert event == event_exp
    assert event.message is event_msg
    assert event.circumstances == ("event", event_msg.event, event_msg.body)

    with timeline.frozen():
        assert timeline.last is event
        assert timeline.history() == initial_history + [some.object.same_as(event)]
        timeline.expect_realized(event_exp)


@pytest.mark.parametrize("outcome", ["success", "failure"])
def test_request_response(make_timeline, outcome):
    timeline, initial_history = make_timeline()
    messages = MessageFactory()

    request_msg = messages.request("next", {"threadId": 3})
    request_exp = expectation_of(request_msg)
    request = timeline.record_request(request_msg)

    assert request == request_exp
    assert request.command == request_msg.command
    assert request.arguments == request_msg.arguments
    assert request.circumstances == (
        "request",
        request_msg.command,
        request_msg.arguments,
    )

    with timeline.frozen():
        assert timeline.last is request
        assert timeline.history() == initial_history + [some.object.same_as(request)]
        timeline.expect_realized(request_exp)
        timeline.expect_realized(Request("next"))

    response_msg = messages.response(
        request_msg, {} if outcome == "success" else Exception("error!")
    )
    response = timeline.record_response(request, response_msg)
    assert response.request is request
    assert response.body == response_msg.body
    if outcome == "success":
        assert response.success
    else:
        assert not response.success
    assert response.circumstances == ("response", request, response_msg.body)

    assert response == Response(request, response_msg.body)
    assert response == Response(request, some.object)
    assert response == Response(request)

    if outcome == "success":
        assert response == Response(request, some.dict)
        assert response != Response(request, some.error)
    else:
        assert response != Response(request, some.dict)
        assert response == Response(request, some.error)

    assert response == Response(request_exp, response_msg.body)
    assert response == Response(request_exp, some.object)
    assert response == Response(request_exp)

    if outcome == "success":
        assert response == Response(request_exp, some.dict)
        assert response != Response(request_exp, some.error)
    else:
        assert response != Response(request_exp, some.dict)
        assert response == Response(request_exp, some.error)

    with timeline.frozen():
        assert timeline.last is response
        assert timeline.history() == initial_history + [
            some.object.same_as(request),
            some.object.same_as(response),
        ]

        timeline.expect_realized(Response(request))
        timeline.expect_realized(Response(request, response_msg.body))
        timeline.expect_realized(Response(request, some.object))

        if outcome == "success":
            timeline.expect_realized(Response(request, some.dict))
            timeline.expect_not_realized(Response(request, some.error))
        else:
            timeline.expect_not_realized(Response(request, some.dict))
            timeline.expect_realized(Response(request, some.error))

        timeline.expect_realized(Response(request))
        timeline.expect_realized(Response(request_exp, response_msg.body))
        timeline.expect_realized(Response(request_exp, some.object))

        if outcome == "success":
            timeline.expect_realized(Response(request_exp, some.dict))
            timeline.expect_not_realized(Response(request_exp, some.error))
        else:
            timeline.expect_not_realized(Response(request_exp, some.dict))
            timeline.expect_realized(Response(request_exp, some.error))


def test_after(make_timeline):
    timeline, _ = make_timeline()
    first = timeline.mark("first")

    second_exp = first >> Mark("second")
    with timeline.frozen():
        assert second_exp not in timeline

    timeline.mark("second")
    with timeline.frozen():
        assert second_exp in timeline

    timeline.mark("first")
    with timeline.frozen():
        assert Mark("second") >> Mark("first") in timeline


def test_before(make_timeline):
    timeline, _ = make_timeline()
    t = timeline.beginning

    first = timeline.mark("first")
    timeline.mark("second")

    with timeline.frozen():
        assert t >> Mark("second") >> Mark("first") not in timeline
        assert Mark("second") >> first not in timeline

    third = timeline.mark("third")

    with timeline.frozen():
        assert t >> Mark("second") >> Mark("first") not in timeline
        assert Mark("second") >> first not in timeline
        assert t >> Mark("second") >> Mark("third") in timeline
        assert Mark("second") >> third in timeline


def test_and(make_timeline):
    eggs_exp = Mark("eggs")
    ham_exp = Mark("ham")
    cheese_exp = Mark("cheese")

    timeline, _ = make_timeline()
    t = timeline.beginning

    with timeline.frozen():
        assert t >> (eggs_exp & ham_exp) not in timeline
        assert t >> (ham_exp & eggs_exp) not in timeline
        assert t >> (cheese_exp & ham_exp & eggs_exp) not in timeline

    timeline.mark("eggs")
    with timeline.frozen():
        assert t >> (eggs_exp & ham_exp) not in timeline
        assert t >> (ham_exp & eggs_exp) not in timeline
        assert t >> (cheese_exp & ham_exp & eggs_exp) not in timeline

    timeline.mark("ham")
    with timeline.frozen():
        assert t >> (eggs_exp & ham_exp) in timeline
        assert t >> (ham_exp & eggs_exp) in timeline
        assert t >> (cheese_exp & ham_exp & eggs_exp) not in timeline

    timeline.mark("cheese")
    with timeline.frozen():
        assert t >> (eggs_exp & ham_exp) in timeline
        assert t >> (ham_exp & eggs_exp) in timeline
        assert t >> (cheese_exp & ham_exp & eggs_exp) in timeline


def test_or(make_timeline):
    eggs_exp = Mark("eggs")
    ham_exp = Mark("ham")
    cheese_exp = Mark("cheese")

    timeline, _ = make_timeline()
    t = timeline.beginning

    with timeline.frozen():
        assert t >> (eggs_exp | ham_exp) not in timeline
        assert t >> (ham_exp | eggs_exp) not in timeline
        assert t >> (cheese_exp | ham_exp | eggs_exp) not in timeline

    timeline.mark("eggs")
    with timeline.frozen():
        assert t >> (eggs_exp | ham_exp) in timeline
        assert t >> (ham_exp | eggs_exp) in timeline
        assert t >> (cheese_exp | ham_exp | eggs_exp) in timeline

    timeline.mark("cheese")
    with timeline.frozen():
        assert t >> (eggs_exp | ham_exp) in timeline
        assert t >> (ham_exp | eggs_exp) in timeline
        assert t >> (cheese_exp | ham_exp | eggs_exp) in timeline

    timeline.mark("ham")
    with timeline.frozen():
        assert t >> (eggs_exp | ham_exp) in timeline
        assert t >> (ham_exp | eggs_exp) in timeline
        assert t >> (cheese_exp | ham_exp | eggs_exp) in timeline
        t = timeline.last

    timeline.mark("cheese")
    with timeline.frozen():
        assert t >> (eggs_exp | ham_exp) not in timeline
        assert t >> (ham_exp | eggs_exp) not in timeline
        assert t >> (cheese_exp | ham_exp | eggs_exp) in timeline


def test_xor(make_timeline):
    eggs_exp = Mark("eggs")
    ham_exp = Mark("ham")
    cheese_exp = Mark("cheese")

    timeline, _ = make_timeline()
    t1 = timeline.beginning

    with timeline.frozen():
        assert t1 >> (eggs_exp ^ ham_exp) not in timeline
        assert t1 >> (ham_exp ^ eggs_exp) not in timeline
        assert t1 >> (cheese_exp ^ ham_exp ^ eggs_exp) not in timeline

    timeline.mark("eggs")
    with timeline.frozen():
        assert t1 >> (eggs_exp ^ ham_exp) in timeline
        assert t1 >> (ham_exp ^ eggs_exp) in timeline
        assert t1 >> (cheese_exp ^ ham_exp ^ eggs_exp) in timeline
        t2 = timeline.last

    timeline.mark("ham")
    with timeline.frozen():
        assert t1 >> (eggs_exp ^ ham_exp) not in timeline
        assert t2 >> (eggs_exp ^ ham_exp) in timeline
        assert t1 >> (ham_exp ^ eggs_exp) not in timeline
        assert t2 >> (ham_exp ^ eggs_exp) in timeline
        assert t1 >> (cheese_exp ^ ham_exp ^ eggs_exp) not in timeline
        assert t2 >> (cheese_exp ^ ham_exp ^ eggs_exp) in timeline


def test_conditional(make_timeline):
    def is_exciting(occ):
        return occ == Event(some.str, "exciting")

    messages = MessageFactory()

    something = Event("something", some.object)
    something_exciting = something.when(is_exciting)
    timeline, _ = make_timeline()
    t = timeline.beginning

    timeline.record_event(messages.event("something", "boring"))
    with timeline.frozen():
        timeline.expect_realized(t >> something)
        timeline.expect_not_realized(t >> something_exciting)

    timeline.record_event(messages.event("something", "exciting"))
    with timeline.frozen():
        timeline.expect_realized(t >> something_exciting)


def test_lower_bound(make_timeline):
    timeline, _ = make_timeline()
    timeline.mark("1")
    timeline.mark("2")
    timeline.mark("3")
    timeline.freeze()

    assert (Mark("2") >> (Mark("1") >> Mark("3"))) not in timeline
    assert (Mark("2") >> (Mark("1") & Mark("3"))) not in timeline
    assert (Mark("2") >> (Mark("1") ^ Mark("3"))) in timeline


@pytest.mark.timeout(3)
def test_frozen(make_timeline, daemon):
    timeline, initial_history = make_timeline()
    assert not timeline.is_frozen

    timeline.freeze()
    assert timeline.is_frozen

    timeline.unfreeze()
    assert not timeline.is_frozen

    with timeline.frozen():
        assert timeline.is_frozen
    assert not timeline.is_frozen

    timeline.mark("dum")

    timeline.freeze()
    assert timeline.is_frozen

    worker_started = threading.Event()
    worker_can_proceed = threading.Event()

    @daemon
    def worker():
        worker_started.set()
        worker_can_proceed.wait()
        timeline.mark("dee")

    worker_started.wait()

    assert Mark("dum") in timeline
    assert Mark("dee") not in timeline

    with timeline.unfrozen():
        worker_can_proceed.set()
        worker.join()

    assert Mark("dee") in timeline


@pytest.mark.timeout(3)
def test_unobserved(make_timeline, daemon):
    timeline, initial_history = make_timeline()

    worker_can_proceed = threading.Event()

    @daemon
    def worker():
        messages = MessageFactory()

        worker_can_proceed.wait()
        worker_can_proceed.clear()
        timeline.record_event(messages.event("dum", {}))
        log.debug("dum")

        worker_can_proceed.wait()
        timeline.record_event(messages.event("dee", {}))
        log.debug("dee")

        timeline.record_event(messages.event("dum", {}))
        log.debug("dum")

    timeline.freeze()
    assert timeline.is_frozen

    timeline.proceed()
    assert not timeline.is_frozen
    worker_can_proceed.set()

    dum = timeline.wait_for_next(Event("dum"))
    assert timeline.is_frozen
    assert dum.observed

    # Should be fine since we observed 'dum' by waiting for it.
    timeline.proceed()
    assert not timeline.is_frozen

    worker_can_proceed.set()
    worker.join()

    dum2 = timeline.wait_for_next(Event("dum"), freeze=False)
    assert not timeline.is_frozen
    assert dum2.observed

    timeline.wait_until_realized(Event("dum") >> Event("dum"), freeze=True)
    assert timeline.is_frozen

    dee = dum.next
    assert not dee.observed

    # Should complain since 'dee' is unobserved.
    with pytest.raises(Exception):
        timeline.proceed()

    # Observe it!
    timeline.expect_realized(Event("dee"))
    assert dee.observed

    # Should be good now.
    timeline.proceed()


def test_new(make_timeline):
    timeline, _ = make_timeline()

    m1 = timeline.mark("1")
    timeline.freeze()

    assert timeline.expect_new(Mark("1")) is m1
    with pytest.raises(Exception):
        timeline.expect_new(Mark("2"))

    timeline.proceed()
    m2 = timeline.mark("2")
    timeline.freeze()

    with pytest.raises(Exception):
        timeline.expect_new(Mark("1"))
    assert timeline.expect_new(Mark("2")) is m2
    with pytest.raises(Exception):
        timeline.expect_new(Mark("3"))

    timeline.unfreeze()
    m3 = timeline.mark("3")
    timeline.freeze()

    with pytest.raises(Exception):
        timeline.expect_new(Mark("1"))
    assert timeline.expect_new(Mark("2")) is m2
    assert timeline.expect_new(Mark("3")) is m3

    timeline.proceed()
    m4 = timeline.mark("4")
    timeline.mark("4")
    timeline.freeze()

    with pytest.raises(Exception):
        timeline.expect_new(Mark("1"))
    with pytest.raises(Exception):
        timeline.expect_new(Mark("2"))
    with pytest.raises(Exception):
        timeline.expect_new(Mark("3"))
    assert timeline.expect_new(Mark("4")) is m4


@pytest.mark.timeout(3)
@pytest.mark.parametrize("order", ["mark_then_wait", "wait_then_mark"])
def test_concurrency(make_timeline, daemon, order):
    timeline, initial_history = make_timeline()

    occurrences = []
    worker_can_proceed = threading.Event()

    @daemon
    def worker():
        worker_can_proceed.wait()
        mark = timeline.mark("tada")
        occurrences.append(mark)

    if order == "mark_then_wait":
        worker_can_proceed.set()
        unblock_worker_later = None
    else:

        @daemon
        def unblock_worker_later():
            time.sleep(0.1)
            worker_can_proceed.set()

    mark = timeline.wait_for_next(Mark("tada"), freeze=True)

    worker.join()
    assert mark is occurrences[0]
    assert timeline.last is mark
    assert timeline.history() == initial_history + occurrences

    if unblock_worker_later:
        unblock_worker_later.join()
