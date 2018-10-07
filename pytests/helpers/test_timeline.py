# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import pytest
import threading
import time

from ptvsd.messaging import RequestFailure

from .pattern import Pattern, ANY, SUCCESS, FAILURE, Is
from .timeline import Timeline, Mark, Event, Request, Response


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
            initial_history = [Is(timeline.beginning)]
            assert timeline.history() == Pattern(initial_history)
        return timeline, initial_history

    yield factory

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
                assert history[-1] == Mark('finalized')
                timeline.close()


@pytest.mark.timeout(1)
def test_occurrences(make_timeline):
    timeline, initial_history = make_timeline()

    mark1 = timeline.mark('dum')
    mark2 = timeline.mark('dee')
    mark3 = timeline.mark('dum')

    assert mark1 == Mark('dum')
    assert mark1.id == 'dum'
    assert mark2 == Mark('dee')
    assert mark2.id == 'dee'
    assert mark3 == Mark('dum')
    assert mark3.id == 'dum'

    with timeline.frozen():
        assert timeline.history() == Pattern(initial_history + [Is(mark1), Is(mark2), Is(mark3)])
        timeline.finalize()

    assert timeline.all_occurrences_of(Mark('dum')) == Pattern((Is(mark1), Is(mark3)))
    assert timeline.all_occurrences_of(Mark('dee')) == Pattern((Is(mark2),))

    assert timeline[:].all_occurrences_of(Mark('dum')) == Pattern((Is(mark1), Is(mark3)))

    # Lower boundary is inclusive.
    assert timeline[mark1:].all_occurrences_of(Mark('dum')) == Pattern((Is(mark1), Is(mark3)))
    assert timeline[mark2:].all_occurrences_of(Mark('dum')) == Pattern((Is(mark3),))
    assert timeline[mark3:].all_occurrences_of(Mark('dum')) == Pattern((Is(mark3),))

    # Upper boundary is exclusive.
    assert timeline[:mark1].all_occurrences_of(Mark('dum')) == ()
    assert timeline[:mark2].all_occurrences_of(Mark('dum')) == Pattern((Is(mark1),))
    assert timeline[:mark3].all_occurrences_of(Mark('dum')) == Pattern((Is(mark1),))


def test_event(make_timeline):
    timeline, initial_history = make_timeline()

    event = timeline.record_event('stopped', {'reason': 'pause'})
    assert event.circumstances == ('Event', 'stopped', {'reason': 'pause'})

    with timeline.frozen():
        assert timeline.last is event
        assert timeline.history() == Pattern(initial_history + [Is(event)])
        timeline.expect_realized(Event('stopped', {'reason': 'pause'}))


@pytest.mark.parametrize('outcome', ['success', 'failure'])
def test_request_response(make_timeline, outcome):
    timeline, initial_history = make_timeline()

    request = timeline.record_request('next', {'threadId': 3})
    request_expectation = Request('next', {'threadId': 3})

    assert request == request_expectation
    assert request.circumstances == ('Request', 'next', {'threadId': 3})
    assert request.command == 'next'
    assert request.arguments == {'threadId': 3}

    with timeline.frozen():
        assert timeline.last is request
        assert timeline.history() == Pattern(initial_history + [Is(request)])
        timeline.expect_realized(Request('next'))
        timeline.expect_realized(Request('next', {'threadId': 3}))

    response_body = {} if outcome == 'success' else RequestFailure('error!')
    response = timeline.record_response(request, response_body)

    assert response == Response(request, response_body)
    assert response == Response(request, ANY)
    if outcome == 'success':
        assert response == Response(request, SUCCESS)
        assert response != Response(request, FAILURE)
    else:
        assert response != Response(request, SUCCESS)
        assert response == Response(request, FAILURE)

    assert response == Response(request_expectation, response_body)
    assert response == Response(request_expectation, ANY)
    if outcome == 'success':
        assert response == Response(request_expectation, SUCCESS)
        assert response != Response(request_expectation, FAILURE)
    else:
        assert response != Response(request_expectation, SUCCESS)
        assert response == Response(request_expectation, FAILURE)

    assert response.circumstances == Pattern(('Response', Is(request), response_body))
    assert response.request is request
    assert response.body == response_body
    if outcome == 'success':
        assert response.success
    else:
        assert not response.success

    with timeline.frozen():
        assert timeline.last is response
        assert timeline.history() == Pattern(initial_history + [Is(request), Is(response)])
        timeline.expect_realized(Response(request, response_body))
        timeline.expect_realized(Response(request, ANY))
        if outcome == 'success':
            timeline.expect_realized(Response(request, SUCCESS))
            timeline.expect_not_realized(Response(request, FAILURE))
        else:
            timeline.expect_not_realized(Response(request, SUCCESS))
            timeline.expect_realized(Response(request, FAILURE))

        timeline.expect_realized(Response(request_expectation, response_body))
        timeline.expect_realized(Response(request_expectation, ANY))
        if outcome == 'success':
            timeline.expect_realized(Response(request_expectation, SUCCESS))
            timeline.expect_not_realized(Response(request_expectation, FAILURE))
        else:
            timeline.expect_not_realized(Response(request_expectation, SUCCESS))
            timeline.expect_realized(Response(request_expectation, FAILURE))


def test_after(make_timeline):
    timeline, _ = make_timeline()
    first = timeline.mark('first')

    second_exp = first >> Mark('second')
    with timeline.frozen():
        assert second_exp not in timeline

    timeline.mark('second')
    with timeline.frozen():
        assert second_exp in timeline


def test_before(make_timeline):
    timeline, _ = make_timeline()
    t = timeline.beginning

    first = timeline.mark('first')
    timeline.mark('second')

    with timeline.frozen():
        assert t >> Mark('second') >> Mark('first') not in timeline
        assert Mark('second') >> first not in timeline

    third = timeline.mark('third')

    with timeline.frozen():
        assert t >> Mark('second') >> Mark('first') not in timeline
        assert Mark('second') >> first not in timeline
        assert t >> Mark('second') >> Mark('third') in timeline
        assert Mark('second') >> third in timeline


def test_and(make_timeline):
    eggs_exp = Mark('eggs')
    ham_exp = Mark('ham')
    cheese_exp = Mark('cheese')

    timeline, _ = make_timeline()
    t = timeline.beginning

    with timeline.frozen():
        assert t >> (eggs_exp & ham_exp) not in timeline
        assert t >> (ham_exp & eggs_exp) not in timeline
        assert t >> (cheese_exp & ham_exp & eggs_exp) not in timeline

    timeline.mark('eggs')
    with timeline.frozen():
        assert t >> (eggs_exp & ham_exp) not in timeline
        assert t >> (ham_exp & eggs_exp) not in timeline
        assert t >> (cheese_exp & ham_exp & eggs_exp) not in timeline

    timeline.mark('ham')
    with timeline.frozen():
        assert t >> (eggs_exp & ham_exp) in timeline
        assert t >> (ham_exp & eggs_exp) in timeline
        assert t >> (cheese_exp & ham_exp & eggs_exp) not in timeline

    timeline.mark('cheese')
    with timeline.frozen():
        assert t >> (eggs_exp & ham_exp) in timeline
        assert t >> (ham_exp & eggs_exp) in timeline
        assert t >> (cheese_exp & ham_exp & eggs_exp) in timeline


def test_or(make_timeline):
    eggs_exp = Mark('eggs')
    ham_exp = Mark('ham')
    cheese_exp = Mark('cheese')

    timeline, _ = make_timeline()
    t = timeline.beginning

    with timeline.frozen():
        assert t >> (eggs_exp | ham_exp) not in timeline
        assert t >> (ham_exp | eggs_exp) not in timeline
        assert t >> (cheese_exp | ham_exp | eggs_exp) not in timeline

    timeline.mark('eggs')
    with timeline.frozen():
        assert t >> (eggs_exp | ham_exp) in timeline
        assert t >> (ham_exp | eggs_exp) in timeline
        assert t >> (cheese_exp | ham_exp | eggs_exp) in timeline

    timeline.mark('cheese')
    with timeline.frozen():
        assert t >> (eggs_exp | ham_exp) in timeline
        assert t >> (ham_exp | eggs_exp) in timeline
        assert t >> (cheese_exp | ham_exp | eggs_exp) in timeline

    timeline.mark('ham')
    with timeline.frozen():
        assert t >> (eggs_exp | ham_exp) in timeline
        assert t >> (ham_exp | eggs_exp) in timeline
        assert t >> (cheese_exp | ham_exp | eggs_exp) in timeline
        t = timeline.last

    timeline.mark('cheese')
    with timeline.frozen():
        assert t >> (eggs_exp | ham_exp) not in timeline
        assert t >> (ham_exp | eggs_exp) not in timeline
        assert t >> (cheese_exp | ham_exp | eggs_exp) in timeline


def test_xor(make_timeline):
    eggs_exp = Mark('eggs')
    ham_exp = Mark('ham')
    cheese_exp = Mark('cheese')

    timeline, _ = make_timeline()
    t1 = timeline.beginning

    with timeline.frozen():
        assert t1 >> (eggs_exp ^ ham_exp) not in timeline
        assert t1 >> (ham_exp ^ eggs_exp) not in timeline
        assert t1 >> (cheese_exp ^ ham_exp ^ eggs_exp) not in timeline

    timeline.mark('eggs')
    with timeline.frozen():
        assert t1 >> (eggs_exp ^ ham_exp) in timeline
        assert t1 >> (ham_exp ^ eggs_exp) in timeline
        assert t1 >> (cheese_exp ^ ham_exp ^ eggs_exp) in timeline
        t2 = timeline.last

    timeline.mark('ham')
    with timeline.frozen():
        assert t1 >> (eggs_exp ^ ham_exp) in timeline
        assert t2 >> (eggs_exp ^ ham_exp) not in timeline
        assert t1 >> (ham_exp ^ eggs_exp) in timeline
        assert t2 >> (ham_exp ^ eggs_exp) not in timeline
        assert t1 >> (cheese_exp ^ ham_exp ^ eggs_exp) in timeline
        assert t2 >> (cheese_exp ^ ham_exp ^ eggs_exp) not in timeline


def test_conditional(make_timeline):
    def is_exciting(occ):
        return occ.circumstances == Pattern(('Event', ANY, 'exciting'))

    something = Event('something', ANY)
    something_exciting = something.when(is_exciting)
    timeline, _ = make_timeline()
    t = timeline.beginning

    timeline.record_event('something', 'boring')
    with timeline.frozen():
        timeline.expect_realized(t >> something)
        timeline.expect_not_realized(t >> something_exciting)

    timeline.record_event('something', 'exciting')
    with timeline.frozen():
        timeline.expect_realized(t >> something_exciting)


@pytest.mark.timeout(1)
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

    timeline.mark('dum')

    timeline.freeze()
    assert timeline.is_frozen

    worker_started = threading.Event()
    worker_can_proceed = threading.Event()
    worker_done = threading.Event()

    @daemon
    def worker():
        worker_started.set()
        worker_can_proceed.wait()
        timeline.mark('dee')
        worker_done.set()

    worker_started.wait()

    assert Mark('dum') in timeline
    assert Mark('dee') not in timeline

    with timeline.unfrozen():
        worker_can_proceed.set()
        worker_done.wait()

    assert Mark('dee') in timeline


@pytest.mark.timeout(1)
def test_unobserved(make_timeline, daemon):
    timeline, initial_history = make_timeline()

    event_recorded = threading.Event()
    worker_can_proceed = threading.Event()

    @daemon
    def worker():
        worker_can_proceed.wait()
        timeline.record_event('dum', {})
        print('dum')

        worker_can_proceed.clear()
        worker_can_proceed.wait()
        timeline.record_event('dee', {})
        print('dee')

        timeline.record_event('dum', {})
        print('dum')
        event_recorded.set()

    timeline.freeze()
    assert timeline.is_frozen

    timeline.proceed()
    assert not timeline.is_frozen
    worker_can_proceed.set()

    dum = timeline.wait_for_next(Event('dum'))
    assert timeline.is_frozen
    assert dum.observed

    # Should be fine since we observed 'dum' by waiting for it.
    timeline.proceed()
    assert not timeline.is_frozen

    worker_can_proceed.set()
    event_recorded.wait()

    dum2 = timeline.wait_for_next(Event('dum'), freeze=False)
    assert not timeline.is_frozen
    assert dum2.observed

    timeline.wait_until_realized(Event('dum') >> Event('dum'), freeze=True)
    assert timeline.is_frozen

    dee = dum.next
    assert not dee.observed

    # Should complain since 'dee' is unobserved.
    with pytest.raises(Exception):
        timeline.proceed()

    # Observe it!
    timeline.expect_realized(Event('dee'))
    assert dee.observed

    # Should be good now.
    timeline.proceed()


@pytest.mark.timeout(1)
@pytest.mark.parametrize('order', ['mark_then_wait', 'wait_then_mark'])
def test_concurrency(make_timeline, daemon, order):
    timeline, initial_history = make_timeline()

    occurrences = []
    worker_can_proceed = threading.Event()
    worker_done = threading.Event()

    @daemon
    def worker():
        worker_can_proceed.wait()
        mark = timeline.mark('tada')
        occurrences.append(mark)
        worker_done.set()

    if order == 'mark_then_wait':
        worker_can_proceed.set()
    else:
        @daemon
        def unblock_worker_later():
            time.sleep(0.1)
            worker_can_proceed.set()

    mark = timeline.wait_for_next(Mark('tada'), freeze=True)

    worker_done.wait()
    assert mark is occurrences[0]
    assert timeline.last is mark
    assert timeline.history() == Pattern(initial_history + occurrences)
