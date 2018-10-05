# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import contextlib
import itertools
import threading

# This is only imported to ensure that the module is actually installed and the
# timeout setting in pytest.ini is active, since otherwise most timeline-based
# tests will hang indefinitely.
import pytest_timeout # noqa

from pytests.helpers import print, timestamp
import pytests.helpers.pattern as pattern


class Timeline(object):
    def __init__(self):
        self._cvar = threading.Condition()
        self.index_iter = itertools.count(1)
        self._last = None
        self._is_frozen = False
        self._is_final = False
        self.beginning = None   # needed for mark() below
        self.beginning = self.mark('begin')

    def assert_frozen(self):
        assert self.is_frozen, 'Timeline can only be inspected while frozen()'

    @property
    def last(self):
        with self._cvar:
            self.assert_frozen()
            return self._last

    def history(self):
        self.assert_frozen()
        return list(self.beginning.and_following())

    def all_occurrences_of(self, expectation):
        occs = [occ for occ in self.history() if occ.realizes(expectation)]
        return tuple(occs)

    def __contains__(self, expectation):
        assert expectation.has_lower_bound, (
            'Expectation must have a lower time bound to be used with "in"! '
            'Use >> to sequence an expectation against an occurrence to establish a lower bound, '
            'or use has_been_realized_in() to test for unbounded expectations in the timeline.'
        )
        return expectation.has_been_realized_in(self)

    def wait_until(self, condition):
        with self._cvar:
            while True:
                with self.frozen():
                    if condition():
                        break
                assert not self._is_final
                self._cvar.wait()
            return self._last

    def wait_for(self, expectation):
        assert expectation.has_lower_bound, (
            'Expectation must have a lower time bound to be used with wait_for()!'
            'Use >> to sequence an expectation against an occurrence to establish a lower bound.'
        )
        print('Waiting for %r' % expectation)
        occ = self.wait_until(lambda: expectation in self)
        print('Expectation %r realized by %r' % (expectation, occ))
        return occ

    def _record(self, occurrence):
        t = timestamp()
        assert isinstance(occurrence, Occurrence)
        assert occurrence.timeline is self
        assert occurrence.timestamp is None
        with self._cvar:
            assert not self._is_final
            occurrence.timestamp = t
            occurrence.index = next(self.index_iter)
            if self._last is None:
                self.beginning = occurrence
                self._last = occurrence
            else:
                occurrence.previous = self._last
                self._last._next = occurrence
                self._last = occurrence
            self._cvar.notify_all()

    @contextlib.contextmanager
    def frozen(self):
        with self._cvar:
            was_frozen = self._is_frozen
            self._is_frozen = True
            yield
            self._is_frozen = was_frozen

    @property
    def is_frozen(self):
        return self._is_frozen

    def finalize(self):
        with self._cvar:
            self._is_final = True
            self._is_frozen = True

    @property
    def is_finalized(self):
        return self._is_finalized

    def __repr__(self):
        with self.frozen():
            return '|' + ' >> '.join(repr(occ) for occ in self.history()) + '|'

    def __str__(self):
        with self.frozen():
            return '\n'.join(repr(occ) for occ in self.history())

    def __data__(self):
        with self.frozen():
            return self.history()

    def mark(self, id):
        occ = Occurrence(self, 'Mark', id)
        occ.id = id
        return occ

    def record_request(self, command, arguments):
        occ = Occurrence(self, 'Request', command, arguments)
        occ.command = command
        occ.arguments = arguments
        occ.wait_for_response = lambda: Response(occ, pattern.ANY).wait()
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


class Expectation(object):
    timeline = None
    has_lower_bound = False

    def is_realized_by(self, occurrence):
        raise NotImplementedError()

    def is_realized_by_any_of(self, occurrences):
        return any(self.is_realized_by(occ) for occ in occurrences)

    def has_been_realized_before(self, occurrence):
        return self.is_realized_by_any_of(occurrence.preceding())

    def has_been_realized_after(self, occurrence):
        return self.is_realized_by_any_of(occurrence.following())

    def has_been_realized_at_or_before(self, occurrence):
        return self.is_realized_by_any_of(occurrence.and_preceding())

    def has_been_realized_at_or_after(self, occurrence):
        return self.is_realized_by_any_of(occurrence.and_following())

    def has_been_realized_in(self, timeline):
        return timeline.all_occurrences_of(self) != ()

    def wait(self):
        assert self.timeline and self.has_lower_bound, (
            'Expectation must belong to a timeline and have a lower time bound to be used wait()! '
            'Use >> to sequence an expectation against an occurrence to establish a lower bound.'
        )
        return self.timeline.wait_for(self)

    def __eq__(self, other):
        if self is other:
            return True
        elif isinstance(other, Occurrence) and self.is_realized_by(other):
            return True
        else:
            return NotImplemented

    def __ne__(self, other):
        return not self == other

    def after(self, other):
        return SequencedExpectation(self, only_after=other)

    def when(self, condition):
        return ConditionalExpectation(self, condition)

    def __rshift__(self, other):
        return self if other is None else other.after(self)

    def __and__(self, other):
        assert isinstance(other, Expectation)
        return AndExpectation(self, other)

    def __or__(self, other):
        assert isinstance(other, Expectation)
        return OrExpectation(self, other)

    def __xor__(self, other):
        assert isinstance(other, Expectation)
        return XorExpectation(self, other)

    def __invert__(self):
        return NotExpectation(self)

    def __repr__(self):
        raise NotImplementedError()


class DerivativeExpectation(Expectation):
    def __init__(self, *expectations):
        self.expectations = expectations
        assert len(expectations) > 0
        assert all(isinstance(exp, Expectation) for exp in expectations)

        timelines = {id(exp.timeline): exp.timeline for exp in expectations}
        timelines.pop(id(None), None)
        if len(timelines) > 1:
            print('Cannot mix expectations from multiple timelines:')
            for tl_id, tl in timelines.items():
                print('\n    %d: %r' % (tl_id, tl))
            print()
            raise ValueError('Cannot mix expectations from multiple timelines')
        for tl in timelines.values():
            self.timeline = tl

    @property
    def has_lower_bound(self):
        return all(exp.has_lower_bound for exp in self.expectations)


class SequencedExpectation(DerivativeExpectation):
    def __init__(self, expectation, only_after):
        super(SequencedExpectation, self).__init__(expectation, only_after)

    @property
    def expectation(self):
        return self.expectations[0]

    @property
    def only_after(self):
        return self.expectations[1]

    def is_realized_by(self, occurrence):
        assert isinstance(occurrence, Occurrence)
        return (
            occurrence.realizes(self.expectation) and
            self.only_after.has_been_realized_before(occurrence)
        )

    @property
    def has_lower_bound(self):
        return self.expectation.has_lower_bound or self.only_after.has_lower_bound

    def __repr__(self):
        return '(%r >> %r)' % (self.only_after, self.expectation)


class NotExpectation(DerivativeExpectation):
    def __init__(self, expectation):
        super(NotExpectation, self).__init__(expectation)

    @property
    def expectation(self):
        return self.expectations[0]

    def is_realized_by(self, occurrence):
        assert isinstance(occurrence, Occurrence)
        return not occurrence.realizes(self.expectation)

    @property
    def has_lower_bound(self):
        return self.expectation.has_lower_bound

    def __repr__(self):
        return '~%r' % self.expectation


class OrExpectation(DerivativeExpectation):
    def is_realized_by(self, occurrence):
        assert isinstance(occurrence, Occurrence)
        return any(occurrence.realizes(exp) for exp in self.expectations)

    def __or__(self, other):
        assert isinstance(other, Expectation)
        return OrExpectation(*(self.expectations + (other,)))

    def __repr__(self):
        return '(' + ' | '.join(repr(exp) for exp in self.expectations) + ')'


class AndExpectation(DerivativeExpectation):
    def is_realized_by(self, occurrence):
        assert isinstance(occurrence, Occurrence)

        # At least one expectation must be realized by the occurrence.
        expectations = list(self.expectations)
        for exp in expectations:
            if occurrence.realizes(exp):
                break
        else:
            return False

        # And then all of the remaining expectations must have been realized
        # at or sometime before that occurrence.
        expectations.remove(exp)
        return all(exp.has_been_realized_at_or_before(occurrence) for exp in expectations)

    @property
    def has_lower_bound(self):
        return any(exp.has_lower_bound for exp in self.expectations)

    def __and__(self, other):
        assert isinstance(other, Expectation)
        return AndExpectation(*(self.expectations + (other,)))

    def __repr__(self):
        return '(' + ' & '.join(repr(exp) for exp in self.expectations) + ')'


class XorExpectation(DerivativeExpectation):
    def is_realized_by(self, occurrence):
        assert isinstance(occurrence, Occurrence)

        # At least one expectation must be realized by the occurrence.
        expectations = list(self.expectations)
        for exp in expectations:
            if occurrence.realizes(exp):
                break
        else:
            return False

        # And then none of the remaining expectations must have been realized
        # at or sometime before that occurrence.
        expectations.remove(exp)
        return not any(exp.has_been_realized_at_or_before(occurrence) for exp in expectations)

    @property
    def has_lower_bound(self):
        return all(exp.has_lower_bound for exp in self.expectations)

    def __xor__(self, other):
        assert isinstance(other, Expectation)
        return XorExpectation(*(self.expectations + (other,)))

    def __repr__(self):
        return '(' + ' ^ '.join(repr(exp) for exp in self.expectations) + ')'


class ConditionalExpectation(DerivativeExpectation):
    def __init__(self, expectation, condition):
        self.condition = condition
        super(ConditionalExpectation, self).__init__(expectation)

    @property
    def expectation(self):
        return self.expectations[0]

    def is_realized_by(self, occurrence):
        assert isinstance(occurrence, Occurrence)
        return self.condition(occurrence) and occurrence.realizes(self.expectation)

    def __repr__(self):
        return '%r?' % self.expectation


class PatternExpectation(Expectation):
    def __init__(self, *circumstances):
        self.circumstances = pattern.Pattern(circumstances)

    def is_realized_by(self, occurrence):
        assert isinstance(occurrence, Occurrence)
        return occurrence.circumstances == self.circumstances

    def __repr__(self):
        circumstances = self.circumstances.pattern
        return '%s%r' % (circumstances[0], circumstances[1:])


def Mark(id):
    return PatternExpectation('Mark', id)


def Request(command, arguments=pattern.ANY):
    return PatternExpectation('Request', command, arguments)


def Response(request, body=pattern.ANY):
    assert isinstance(request, Expectation) or isinstance(request, Occurrence)
    exp = PatternExpectation('Response', request, body)
    exp.timeline = request.timeline
    exp.has_lower_bound = request.has_lower_bound
    return exp


def Event(event, body=pattern.ANY):
    return PatternExpectation('Event', event, body)


class Occurrence(Expectation):
    has_lower_bound = True

    def __init__(self, timeline, *circumstances):
        assert circumstances
        self.timeline = timeline
        self.previous = None
        self._next = None
        self.timestamp = None
        self.index = None
        self.circumstances = circumstances
        timeline._record(self)
        assert self.timestamp is not None

    @property
    def next(self):
        with self.timeline.frozen():
            occ = self._next
            was_last = occ is self.timeline.last
        if was_last:
            # The .next property of the last occurrence in a timeline can change
            # at any moment when timeline isn't frozen. So if it wasn't frozen by
            # the caller, this was an unsafe operation, and we should complain.
            self.timeline.assert_frozen()
        return occ

    def preceding(self):
        it = self.and_preceding()
        next(it)
        return it

    def and_preceding(self, up_to=None):
        assert up_to is None or isinstance(up_to, Expectation)
        if isinstance(up_to, Occurrence):
            assert self > up_to
        occ = self
        while occ != up_to:
            yield occ
            occ = occ.previous

    def following(self):
        self.timeline.assert_frozen()
        it = self.and_following()
        next(it)
        return it

    def and_following(self, up_to=None):
        assert up_to is None or isinstance(up_to, Expectation)
        self.timeline.assert_frozen()
        if isinstance(up_to, Occurrence):
            assert self < up_to
        occ = self
        while occ != up_to:
            yield occ
            occ = occ.next

    def precedes(self, occurrence):
        assert isinstance(occurrence, Occurrence)
        return any(occ is self for occ in occurrence.preceding())

    def follows(self, occurrence):
        assert isinstance(occurrence, Occurrence)
        return any(occ is self for occ in occurrence.following())

    def realizes(self, expectation):
        assert isinstance(expectation, Expectation)
        return expectation.is_realized_by(self)

    def is_realized_by(self, other):
        return self is other

    def __lt__(self, occurrence):
        return self.precedes(occurrence)

    def __gt__(self, occurrence):
        return self.follows(occurrence)

    def __le__(self, occurrence):
        return self is occurrence or self < occurrence

    def __ge__(self, occurrence):
        return self is occurrence or self > occurrence

    def __rshift__(self, expectation):
        assert isinstance(expectation, Expectation)
        return expectation.after(self)

    def __hash__(self):
        return hash(id(self))

    def __data__(self):
        return self.circumstances

    def __repr__(self):
        return '%d!%s%r' % (self.index, self.circumstances[0], self.circumstances[1:])