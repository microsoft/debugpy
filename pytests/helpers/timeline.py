# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import threading
import time

import pytests.helpers.pattern as pattern


class Timeline(object):
    def __init__(self):
        self._cvar = threading.Condition()
        self._is_frozen = False
        self._last = None
        self.beginning = self.mark('begin')

    def last(self):
        with self._cvar:
            return self._last

    def history(self):
        result = list(self.last().backtrack())
        result.reverse()
        return result

    def __contains__(self, expectations):
        try:
            iter(expectations)
        except TypeError:
            expectations = (expectations,)
        assert all(isinstance(exp, Expectation) for exp in expectations)
        last = self.last()
        return all(exp.has_occurred_by(last) for exp in expectations)

    def _record(self, occurrence):
        assert isinstance(occurrence, Occurrence)
        assert occurrence.timeline is self
        assert occurrence.preceding is None
        with self._cvar:
            assert not self._is_frozen
            occurrence.timestamp = time.clock()
            occurrence.preceding = self._last
            self._last = occurrence
            self._cvar.notify_all()

    def freeze(self):
        with self._cvar:
            self._is_frozen = True

    def wait_until(self, expectation):
        assert isinstance(expectation, Expectation)
        with self._cvar:
            while expectation not in self:
                self._cvar.wait()
            return self._last

    def __repr__(self):
        return '|' + ' >> '.join(repr(occ) for occ in self.history()) + '|'

    def __str__(self):
        return '\n'.join(repr(occ) for occ in self.history())

    def __data__(self):
        return self.history()

    def mark(self, id):
        occ = Occurrence(self, 'Mark', id)
        occ.id = id
        return occ

    def record_request(self, command, arguments):
        occ = Occurrence(self, 'Request', command, arguments)
        occ.command = command
        occ.arguments = arguments

        def wait_for_response():
            self.wait_until(Response(occ, pattern.ANY))

        occ.wait_for_response = wait_for_response
        return occ

    def record_response(self, request, body):
        assert isinstance(request, Occurrence)
        occ = Occurrence(self, 'Response', request, body)
        occ.request = request
        occ.body = body
        occ.success = not isinstance(occ.body, Exception)
        return occ

    def record_event(self, event, body):
        occ = Occurrence(self, 'Event', event, body)
        occ.event = event
        occ.body = body
        return occ


class Occurrence(object):
    def __init__(self, timeline, *circumstances):
        assert circumstances
        self.timeline = timeline
        self.preceding = None
        self.timestamp = None
        self.circumstances = circumstances
        timeline._record(self)
        assert self.timestamp is not None

    def backtrack(self, until=None):
        assert until is None or isinstance(until, Occurrence)
        occ = self
        while occ is not until:
            yield occ
            occ = occ.preceding

    def precedes(self, occurrence):
        assert isinstance(occurrence, Occurrence)
        preceding = occurrence.backtrack()
        next(preceding)
        return any(occ is self for occ in preceding)

    def follows(self, occurrence):
        assert isinstance(occurrence, Occurrence)
        return occurrence.precedes(self)

    def __lt__(self, occurrence):
        return self.precedes(occurrence)

    def __gt__(self, occurrence):
        return self.follows(occurrence)

    def __le__(self, occurrence):
        return self == occurrence or self < occurrence

    def __ge__(self, occurrence):
        return self == occurrence or self > occurrence

    def __rshift__(self, expectation):
        assert isinstance(expectation, Expectation)
        return expectation.after(self)

    def __hash__(self):
        return hash(id(self))

    def __data__(self):
        return self.circumstances

    def __repr__(self):
        timestamp = int(self.timestamp * 100000)
        return '@%06d:%s%r' % (timestamp, self.circumstances[0], self.circumstances[1:])


class Expectation(object):
    def has_occurred_by(self, occurrence):
        raise NotImplementedError()

    def after(self, other):
        return BoundedExpectation(self, must_follow=other)

    def before(self, other):
        return BoundedExpectation(self, must_precede=other)

    def when(self, condition):
        return ConditionalExpectation(self, condition)

    def __rshift__(self, other):
        return self.before(other)

    def __and__(self, other):
        assert isinstance(other, Expectation)
        return AndExpectation(self, other)

    def __or__(self, other):
        assert isinstance(other, Expectation)
        return OrExpectation(self, other)

    def __xor__(self, other):
        assert isinstance(other, Expectation)
        return XorExpectation(self, other)

    def __repr__(self):
        raise NotImplementedError()


class BoundedExpectation(Expectation):
    def __init__(self, expectation, must_follow=None, must_precede=None):
        self.expectation = expectation
        self.must_follow = Occurred(must_follow) if isinstance(must_follow, Occurrence) else must_follow
        self.must_precede = Occurred(must_precede) if isinstance(must_precede, Occurrence) else must_precede
        assert isinstance(self.expectation, Expectation)
        assert self.must_follow is None or isinstance(self.must_follow, Expectation)
        assert self.must_precede is None or isinstance(self.must_precede, Expectation)

    def has_occurred_by(self, occurrence):
        assert isinstance(occurrence, Occurrence)

        expectation = self.expectation
        must_follow = self.must_follow
        must_precede = self.must_precede
        occ = occurrence

        if must_precede is not None:
            for occ in occ.backtrack():
                if not must_precede.has_occurred_by(occ):
                    break
            else:
                return False

        for occ in occ.backtrack():
            if expectation.has_occurred_by(occ):
                break
        else:
            return False

        return must_follow is None or must_follow.has_occurred_by(occ)

    def __repr__(self):
        s = '('
        if self.must_follow is not None:
            s += repr(self.must_follow) + ' >> '
        s += repr(self.expectation)
        if self.must_precede is not None:
            s += ' >> ' + repr(self.must_precede)
        s += ')'
        return s


class AndExpectation(Expectation):
    def __init__(self, *expectations):
        assert len(expectations) > 0
        assert all(isinstance(exp, Expectation) for exp in expectations)
        self.expectations = expectations

    def has_occurred_by(self, occurrence):
        assert isinstance(occurrence, Occurrence)
        return all(exp.has_occurred_by(occurrence) for exp in self.expectations)

    def __and__(self, other):
        assert isinstance(other, Expectation)
        return AndExpectation(*(self.expectations + (other,)))

    def __repr__(self):
        return '(' + ' & '.join(repr(exp) for exp in self.expectations) + ')'


class OrExpectation(Expectation):
    def __init__(self, *expectations):
        assert len(expectations) > 0
        assert all(isinstance(exp, Expectation) for exp in expectations)
        self.expectations = expectations

    def has_occurred_by(self, occurrence):
        assert isinstance(occurrence, Occurrence)
        return any(exp.has_occurred_by(occurrence) for exp in self.expectations)

    def __or__(self, other):
        assert isinstance(other, Expectation)
        return OrExpectation(*(self.expectations + (other,)))

    def __repr__(self):
        return '(' + ' | '.join(repr(exp) for exp in self.expectations) + ')'


class XorExpectation(Expectation):
    def __init__(self, *expectations):
        assert len(expectations) > 0
        assert all(isinstance(exp, Expectation) for exp in expectations)
        self.expectations = expectations

    def has_occurred_by(self, occurrence):
        assert isinstance(occurrence, Occurrence)
        return sum(exp.has_occurred_by(occurrence) for exp in self.expectations) == 1

    def __xor__(self, other):
        assert isinstance(other, Expectation)
        return XorExpectation(*(self.expectations + (other,)))

    def __repr__(self):
        return '(' + ' ^ '.join(repr(exp) for exp in self.expectations) + ')'


class ConditionalExpectation(Expectation):
    def __init__(self, expectation, condition):
        assert isinstance(expectation, Expectation)
        self.expectation = expectation
        self.condition = condition

    def has_occurred_by(self, occurrence):
        assert isinstance(occurrence, Occurrence)
        return self.condition(occurrence) and self.expectation.has_occurred_by(occurrence)

    def __repr__(self):
        return '%r?' % self.expectation


class BasicExpectation(Expectation):
    def __init__(self, *circumstances):
        self.circumstances = pattern.Pattern(circumstances)

    def has_occurred_by(self, occurrence):
        assert isinstance(occurrence, Occurrence)
        return any(
            occ.circumstances
            in self.circumstances
            for occ in occurrence.backtrack()
        )

    def __repr__(self):
        circumstances = self.circumstances.pattern
        return '%s%r' % (circumstances[0], circumstances[1:])


class Occurred(BasicExpectation):
    def __init__(self, occurrence):
        assert isinstance(occurrence, Occurrence)
        self.occurrence = occurrence

    def has_occurred_by(self, occurrence):
        assert isinstance(occurrence, Occurrence)
        return any(occ is self.occurrence for occ in occurrence.backtrack())

    def __repr__(self):
        return 'Occurred(%r)' % self.occurrence


def Mark(id):
    return BasicExpectation('Mark', id)


def Request(command, arguments=pattern.ANY):
    return BasicExpectation('Request', command, arguments)


def Response(request, body=pattern.ANY):
    assert isinstance(request, Expectation) or isinstance(request, Occurrence)
    return BasicExpectation('Response', request, body)


def Event(event, body=pattern.ANY):
    return BasicExpectation('Event', event, body)
