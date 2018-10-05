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
def make_timeline():
    """Provides a timeline factory. All timelines created by this factory
    are automatically frozen and checked for basic consistency after the
    end of the test.
    """

    timelines = []

    def factory():
        timeline = Timeline()
        timelines.append(timeline)
        return timeline

    yield factory

    for timeline in timelines:
        timeline.finalize()
        history = timeline.history()
        history.sort(key=lambda occ: occ.timestamp)
        assert history == timeline.history()


def history_data(timeline):
    with timeline.frozen():
        return [occ.__data__() for occ in timeline.history()]


def test_simple_1thread(make_timeline):
    timeline = make_timeline()
    expected_history = history_data(timeline)

    with timeline.frozen():
        assert timeline.all_occurrences_of(Mark('tada')) == ()
        assert not Mark('tada').has_been_realized_in(timeline)

    mark = timeline.mark('tada')
    expected_history += [('Mark', 'tada')]

    assert mark.circumstances == ('Mark', 'tada')
    assert mark.id == 'tada'
    with timeline.frozen():
        assert timeline.history() == Pattern(expected_history)
        assert timeline.all_occurrences_of(Mark('tada')) == Pattern((Is(mark),))
        assert timeline.last is mark
        assert Mark('tada').has_been_realized_in(timeline)

    request = timeline.record_request('next', {'threadId': 3})
    expected_history += [('Request', 'next', {'threadId': 3})]

    assert request.circumstances == ('Request', 'next', {'threadId': 3})
    assert request.command == 'next'
    assert request.arguments == {'threadId': 3}
    with timeline.frozen():
        assert timeline.history() == Pattern(expected_history)
        assert timeline.last is request
        assert Request('next', {'threadId': 3}).has_been_realized_in(timeline)
        assert timeline.all_occurrences_of(Request('next', {'threadId': 3})) == Pattern((Is(request),))

    response = timeline.record_response(request, {})
    expected_history += [('Response', Is(request), {})]

    assert response.circumstances == Pattern(('Response', Is(request), {}))
    assert response.request is request
    assert response.body == {}
    assert response.success
    expectations = [
        Response(request, {}),
        Response(request, SUCCESS),
        Response(request),
        Response(Request('next', {'threadId': 3}), {}),
        Response(Request('next', {'threadId': 3}), SUCCESS),
        Response(Request('next', {'threadId': 3})),
    ]
    with timeline.frozen():
        assert timeline.history() == Pattern(expected_history)
        assert timeline.last is response
        for exp in expectations:
            print(exp)
            assert exp.has_been_realized_in(timeline)
            print(timeline.all_occurrences_of(exp))
            assert timeline.all_occurrences_of(exp) == Pattern((Is(response),))

    event = timeline.record_event('stopped', {'reason': 'pause'})
    expected_history += [('Event', 'stopped', {'reason': 'pause'})]

    assert event.circumstances == ('Event', 'stopped', {'reason': 'pause'})
    with timeline.frozen():
        assert timeline.last is event
        assert timeline.history() == Pattern(expected_history)
        assert Event('stopped', {'reason': 'pause'}).has_been_realized_in(timeline)
        assert timeline.all_occurrences_of(Event('stopped', {'reason': 'pause'})) == Pattern((Is(event),))

    request2 = timeline.record_request('next', {'threadId': 6})
    expected_history += [('Request', 'next', {'threadId': 6})]
    response2 = timeline.record_response(request2, RequestFailure('error!'))
    expected_history += [('Response', Is(request2), FAILURE)]

    assert response2.circumstances == Pattern(('Response', Is(request2), FAILURE))
    assert response2.request is request2
    assert isinstance(response2.body, RequestFailure) and response2.body.message == 'error!'
    assert not response2.success
    expectations = [
        Response(request2, RequestFailure('error!')),
        Response(request2, FAILURE),
        Response(request2),
        Response(Request('next', {'threadId': 6}), RequestFailure('error!')),
        Response(Request('next', {'threadId': 6}), FAILURE),
        Response(Request('next', {'threadId': 6})),
    ]
    with timeline.frozen():
        for exp in expectations:
            print(exp)
            assert exp.has_been_realized_in(timeline)
            assert timeline.all_occurrences_of(exp) == Pattern((Is(response2),))
        assert timeline.all_occurrences_of(Response(Request('next'))) == Pattern((Is(response), Is(response2)))


@pytest.mark.parametrize('occurs_before_wait', (True, False))
def test_simple_mthread(make_timeline, daemon, occurs_before_wait):
    timeline = make_timeline()
    expected_history = history_data(timeline)
    thev = threading.Event()
    occurrences = []

    @daemon
    def worker():
        thev.wait()
        thev.clear()
        mark = timeline.mark('tada')
        occurrences.append(mark)

        thev.wait()
        thev.clear()
        request = timeline.record_request('next', {'threadId': 3})
        occurrences.append(request)

        thev.wait()
        thev.clear()
        response = timeline.record_response(request, {})
        occurrences.append(response)

        thev.wait()
        thev.clear()
        event = timeline.record_event('stopped', {'reason': 'pause'})
        occurrences.append(event)

    def advance_worker():
        if occurs_before_wait:
            thev.set()
        else:
            def set_later():
                time.sleep(0.1)
                thev.set()
            threading.Thread(target=set_later).start()

    t = timeline.beginning

    advance_worker()
    expectation = Mark('tada')
    expected_history += [('Mark', 'tada')]
    t = (t >> expectation).wait()

    with timeline.frozen():
        assert expectation.has_been_realized_in(timeline)
        assert timeline.history() == Pattern(expected_history)

    advance_worker()
    expected_history += [('Request', 'next', {'threadId': 3})]
    expectation = Request('next', {'threadId': 3})
    t = (t >> expectation).wait()

    with timeline.frozen():
        assert expectation.has_been_realized_in(timeline)
        assert timeline.history() == Pattern(expected_history)
        request = occurrences[-1]
        assert request is t

    advance_worker()
    expected_history += [('Response', request, {})]
    expectation = Response(request, {}) & Response(Request('next', {'threadId': 3}), {})
    t = (t >> expectation).wait()

    with timeline.frozen():
        assert expectation.has_been_realized_in(timeline)
        assert timeline.history() == Pattern(expected_history)

    advance_worker()
    expected_history += [('Event', 'stopped', {'reason': 'pause'})]
    expectation = Event('stopped', {'reason': 'pause'})

    with timeline.frozen():
        t = (t >> expectation).wait()
        assert expectation.has_been_realized_in(timeline)
        assert timeline.history() == Pattern(expected_history)


def test_after(make_timeline):
    timeline = make_timeline()
    first = timeline.mark('first')

    second_exp = first >> Mark('second')
    with timeline.frozen():
        assert second_exp not in timeline

    timeline.mark('second')
    with timeline.frozen():
        assert second_exp in timeline


def test_before(make_timeline):
    timeline = make_timeline()
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


def test_not(make_timeline):
    timeline = make_timeline()
    timeline.mark('other')

    with timeline.frozen():
        assert timeline.beginning >> ~Mark('something') in timeline
        t = timeline.last

    timeline.mark('something')

    with timeline.frozen():
        assert timeline.beginning >> ~Mark('something') in timeline
        assert t >> ~Mark('something') not in timeline


def test_and(make_timeline):
    eggs_exp = Mark('eggs')
    ham_exp = Mark('ham')
    cheese_exp = Mark('cheese')

    timeline = make_timeline()
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

    timeline = make_timeline()
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

    timeline = make_timeline()
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
    timeline = make_timeline()
    t = timeline.beginning

    timeline.record_event('something', 'boring')
    with timeline.frozen():
        assert t >> something in timeline
        assert t >> something_exciting not in timeline

    timeline.record_event('something', 'exciting')
    with timeline.frozen():
        assert t >> something_exciting in timeline
