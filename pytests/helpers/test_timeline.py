# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import pytest
import threading
import time

from ptvsd.messaging import RequestFailure

from .pattern import Pattern, ANY, SUCCESS, FAILURE
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
        assert Mark(Pattern('begin')) in timeline
        assert timeline.history() in Pattern([('Mark', 'begin',)])
        timelines.append(timeline)
        return timeline

    yield factory

    for timeline in timelines:
        timeline.freeze()
        history = list(timeline.history())
        history.sort(key=lambda occ: occ.timestamp)
        assert history == timeline.history()


def history_data(timeline):
    return [occ.__data__() for occ in timeline.history()]


def test_simple_1thread(make_timeline):
    timeline = make_timeline()
    expected_history = history_data(timeline)
    expectations = []

    mark = timeline.mark('tada')
    assert mark.circumstances == ('Mark', 'tada')
    assert mark.id == 'tada'
    expectations += [Mark('tada')]
    assert expectations in timeline
    expected_history += [('Mark', 'tada')]
    assert timeline.history() in Pattern(expected_history)

    request = timeline.record_request('next', {'threadId': 3})
    assert request.circumstances == ('Request', 'next', {'threadId': 3})
    assert request.command == 'next'
    assert request.arguments == {'threadId': 3}
    expectations += [Request('next', {'threadId': 3})]
    assert expectations in timeline
    expected_history += [('Request', 'next', {'threadId': 3})]
    assert timeline.history() in Pattern(expected_history)

    response = timeline.record_response(request, {})
    assert response.circumstances == ('Response', request, {})
    assert response.request is request
    assert response.body == {}
    assert response.success
    expectations += [
        Response(request, {}),
        Response(request, SUCCESS),
        Response(Request('next', {'threadId': 3}), {}),
        Response(Request('next', {'threadId': 3}), SUCCESS),
    ]
    assert expectations in timeline
    expected_history += [('Response', request, {})]
    assert timeline.history() in Pattern(expected_history)

    event = timeline.record_event('stopped', {'reason': 'pause'})
    assert event.circumstances == ('Event', 'stopped', {'reason': 'pause'})
    expectations += [Event('stopped', {'reason': 'pause'})]
    assert expectations in timeline
    expected_history += [('Event', 'stopped', {'reason': 'pause'})]
    assert timeline.history() in Pattern(expected_history)

    request = timeline.record_request('next', {'threadId': 6})
    expected_history += [('Request', 'next', {'threadId': 6})]

    response = timeline.record_response(request, RequestFailure('error!'))
    assert response.circumstances in Pattern((
        'Response',
        request,
        ANY.such_that(lambda err: isinstance(err, RequestFailure) and err.message == 'error!')
    ))
    assert response.request is request
    assert isinstance(response.body, RequestFailure) and response.body.message == 'error!'
    assert not response.success
    expectations += [
        Response(request, FAILURE),
        Response(Request('next', {'threadId': 6}), FAILURE),
    ]
    assert expectations in timeline
    expected_history += [('Response', request, FAILURE)]
    assert timeline.history() in Pattern(expected_history)


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

    advance_worker()
    expectation = Mark('tada')
    timeline.wait_until(expectation)
    assert expectation in timeline
    expected_history += [('Mark', 'tada')]
    assert timeline.history() in Pattern(expected_history)

    advance_worker()
    expectation = Request('next', {'threadId': 3})
    timeline.wait_until(expectation)
    assert expectation in timeline
    expected_history += [('Request', 'next', {'threadId': 3})]
    assert timeline.history() in Pattern(expected_history)
    request = occurrences[-1]

    advance_worker()
    expectation = Response(request, {}) & Response(Request('next', {'threadId': 3}), {})
    timeline.wait_until(expectation)
    assert expectation in timeline
    expected_history += [('Response', request, {})]
    assert timeline.history() in Pattern(expected_history)

    advance_worker()
    expectation = Event('stopped', {'reason': 'pause'})
    timeline.wait_until(expectation)
    assert expectation in timeline
    expected_history += [('Event', 'stopped', {'reason': 'pause'})]
    assert timeline.history() in Pattern(expected_history)


def test_and(make_timeline):
    eggs_exp = Mark('eggs')
    ham_exp = Mark('ham')
    cheese_exp = Mark('cheese')

    timeline = make_timeline()
    assert eggs_exp & ham_exp not in timeline
    assert ham_exp & eggs_exp not in timeline
    assert cheese_exp & ham_exp & eggs_exp not in timeline

    timeline.mark('eggs')
    assert eggs_exp & ham_exp not in timeline
    assert ham_exp & eggs_exp not in timeline
    assert cheese_exp & ham_exp & eggs_exp not in timeline

    timeline.mark('ham')
    assert eggs_exp & ham_exp in timeline
    assert ham_exp & eggs_exp in timeline
    assert cheese_exp & ham_exp & eggs_exp not in timeline

    timeline.mark('cheese')
    assert eggs_exp & ham_exp in timeline
    assert ham_exp & eggs_exp in timeline
    assert cheese_exp & ham_exp & eggs_exp in timeline


def test_or(make_timeline):
    eggs_exp = Mark('eggs')
    ham_exp = Mark('ham')
    cheese_exp = Mark('cheese')

    timeline = make_timeline()
    assert eggs_exp | ham_exp not in timeline
    assert ham_exp | eggs_exp not in timeline
    assert cheese_exp | ham_exp | eggs_exp not in timeline

    timeline.mark('eggs')
    assert eggs_exp | ham_exp in timeline
    assert ham_exp | eggs_exp in timeline
    assert cheese_exp | ham_exp | eggs_exp in timeline

    timeline.mark('cheese')
    assert eggs_exp | ham_exp in timeline
    assert ham_exp | eggs_exp in timeline
    assert cheese_exp | ham_exp | eggs_exp in timeline

    timeline = make_timeline()

    timeline.mark('ham')
    assert eggs_exp | ham_exp in timeline
    assert ham_exp | eggs_exp in timeline
    assert cheese_exp | ham_exp | eggs_exp in timeline

    timeline = make_timeline()

    timeline.mark('cheese')
    assert eggs_exp | ham_exp not in timeline
    assert ham_exp | eggs_exp not in timeline
    assert cheese_exp | ham_exp | eggs_exp in timeline


def test_xor(make_timeline):
    eggs_exp = Mark('eggs')
    ham_exp = Mark('ham')
    cheese_exp = Mark('cheese')

    timeline = make_timeline()
    assert eggs_exp ^ ham_exp not in timeline
    assert ham_exp ^ eggs_exp not in timeline
    assert cheese_exp ^ ham_exp ^ eggs_exp not in timeline

    timeline.mark('eggs')
    assert eggs_exp ^ ham_exp in timeline
    assert ham_exp ^ eggs_exp in timeline
    assert cheese_exp ^ ham_exp ^ eggs_exp in timeline

    timeline.mark('ham')
    assert eggs_exp ^ ham_exp not in timeline
    assert ham_exp ^ eggs_exp not in timeline
    assert cheese_exp ^ ham_exp ^ eggs_exp not in timeline


def test_conditional(make_timeline):
    def is_exciting(occ):
        return occ.circumstances in Pattern(('Event', ANY, 'exciting'))

    something = Event('something', ANY)
    something_exciting = something.when(is_exciting)
    timeline = make_timeline()

    timeline.record_event('something', 'boring')
    assert something in timeline
    assert something_exciting not in timeline

    timeline.record_event('something', 'exciting')
    assert something_exciting in timeline


def test_after(make_timeline):
    timeline = make_timeline()
    first = timeline.mark('first')

    second_exp = first >> Mark('second')
    assert second_exp not in timeline

    timeline.mark('second')
    assert second_exp in timeline


def test_before(make_timeline):
    timeline = make_timeline()
    first = timeline.mark('first')

    timeline.mark('second')
    assert Mark('second') >> Mark('first') not in timeline
    assert Mark('second') >> first not in timeline

    third = timeline.mark('third')
    assert Mark('second') >> Mark('first') not in timeline
    assert Mark('second') >> first not in timeline
    assert Mark('second') >> Mark('third') in timeline
    assert Mark('second') >> third in timeline


