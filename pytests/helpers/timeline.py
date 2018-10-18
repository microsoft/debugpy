# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import print_function, with_statement, absolute_import

import contextlib
import itertools
import threading

from ptvsd.compat import queue

from pytests.helpers import colors, pattern, print, timestamp


class Timeline(object):
    def __init__(self, ignore_unobserved=None):
        self._ignore_unobserved = ignore_unobserved or []

        self._index_iter = itertools.count(1)
        self._accepting_new = threading.Event()
        self._finalized = threading.Event()
        self._recorded_new = threading.Condition()
        self._record_queue = queue.Queue()

        self._recorder_thread = threading.Thread(target=self._recorder_worker, name='Timeline-%d recorder' % id(self))
        self._recorder_thread.daemon = True
        self._recorder_thread.start()

        # Set up initial environment for our first mark()
        self._last = None
        self._beginning = None
        self._accepting_new.set()

        self._beginning = self.mark('begin')
        assert self._last is self._beginning
        self._proceeding_from = self._beginning

    def expect_frozen(self):
        if not self.is_frozen:
            raise Exception('Timeline can only be inspected while frozen.')

    def __iter__(self):
        return self._beginning.and_following()

    def __len__(self):
        return len(self.history())

    @property
    def beginning(self):
        return self._beginning

    @property
    def last(self):
        self.expect_frozen()
        return self._last

    def history(self):
        self.expect_frozen()
        return list(iter(self))

    def __contains__(self, expectation):
        self.expect_frozen()
        return expectation.is_realized_in(self)

    def all_occurrences_of(self, expectation):
        return tuple(occ for occ in self if occ == expectation)

    def __getitem__(self, index):
        assert isinstance(index, slice)
        assert index.step is None
        return Interval(self, index.start, index.stop)

    def __reversed__(self):
        self.expect_frozen()
        return self.last.and_preceding()

    @property
    def ignore_unobserved(self):
        return self._ignore_unobserved

    @ignore_unobserved.setter
    def ignore_unobserved(self, expectations):
        self.expect_frozen()
        self._ignore_unobserved = expectations

    @property
    def is_frozen(self):
        return not self._accepting_new.is_set()

    def freeze(self):
        self._accepting_new.clear()

    def unfreeze(self):
        if not self.is_final:
            self._accepting_new.set()

    @contextlib.contextmanager
    def frozen(self):
        was_frozen = self.is_frozen
        self.freeze()
        yield
        if not was_frozen and not self.is_final:
            self.unfreeze()

    @contextlib.contextmanager
    def unfrozen(self):
        was_frozen = self.is_frozen
        self.unfreeze()
        yield
        if was_frozen or self.is_final:
            self.freeze()

    @property
    def is_final(self):
        return self._finalized.is_set()

    def finalize(self):
        if self.is_final:
            return

        print(colors.LIGHT_MAGENTA + 'Finalizing' + colors.RESET)
        with self.unfrozen():
            self.mark('finalized')

        with self.unfrozen():
            self._finalized.set()
            # Drain the record queue.
            self._record_queue.join()
            # Tell the recorder to shut itself down.
            self._record_queue.put(None)
            self._recorder_thread.join()

        assert self._record_queue.empty(), 'Finalized timeline had pending records'

    def close(self):
        self.finalize()
        self[:].expect_no_unobserved()

    def __enter__(self):
        return self

    def __leave__(self, *args):
        self.close()

    def observe(self, *occurrences):
        for occ in occurrences:
            occ.observed = True

    def observe_all(self, expectation):
        self.expect_frozen()
        self.observe(*[occ for occ in self if occ == expectation])

    def wait_until(self, condition, freeze=None):
        try:
            # First, test the condition against the timeline as it currently is.
            with self.frozen():
                last_seen = self.last
                if condition(last_seen):
                    return last_seen

            # Now keep spinning waiting for new occurrences to come, and test the
            # condition against every new batch in turn.

            freeze = freeze or self.is_frozen
            self.unfreeze()

            with self._recorded_new:
                while True:
                    with self.frozen():
                        for occ in last_seen.following():
                            if condition(occ):
                                return occ
                        last_seen = self.last

                    assert not self.is_final
                    self._recorded_new.wait()

        finally:
            if freeze:
                self.freeze()


    def wait_for(self, expectation, freeze=None, explain=True):
        assert expectation.has_lower_bound, (
            'Expectation must have a lower time bound to be used with wait_for()! '
            'Use >> to sequence an expectation against an occurrence to establish a lower bound, '
            'or wait_for_next() to wait for the next expectation since the timeline was last '
            'frozen, or wait_until_realized() when a lower bound is really not necessary.'
        )
        return self.wait_until_realized(expectation, freeze, explain=explain)

    def wait_until_realized(self, expectation, freeze=None, explain=True, observe=True):
        if explain:
            print(colors.LIGHT_MAGENTA + 'Waiting for ' + colors.RESET + colors.color_repr(expectation))

        reasons = {}
        check_past = [True]

        def has_been_realized(occ):
            # First time wait_until() calls us, we have to check the whole timeline.
            # On subsequent calls, we only need to check the newly added occurrence.
            if check_past:
                if explain:
                    print(
                        colors.LIGHT_MAGENTA + 'Testing ' + colors.RESET +
                        colors.color_repr(expectation) +
                        colors.LIGHT_MAGENTA + ' against timeline up to and including ' + colors.RESET +
                        colors.color_repr(occ)
                    )
                reasons.update(expectation.test_at_or_before(occ) or {})
                del check_past[:]
            else:
                if explain:
                    print(
                        colors.LIGHT_MAGENTA + 'Testing ' + colors.RESET +
                        colors.color_repr(expectation) +
                        colors.LIGHT_MAGENTA + ' against ' + colors.RESET +
                        colors.color_repr(occ)
                    )
                reasons.update(expectation.test_at(occ) or {})

            if reasons:
                if observe:
                    self.expect_realized(expectation, explain=explain, observe=observe)
                return True
            else:
                if explain:
                    print(
                        colors.color_repr(occ) +
                        colors.LIGHT_MAGENTA + ' did not realize ' + colors.RESET +
                        colors.color_repr(expectation)
                    )

        self.wait_until(has_been_realized, freeze)

        realized_at = reasons[expectation]
        return realized_at

    def wait_for_next(self, expectation, freeze=True, explain=True, observe=True):
        return self.wait_until_realized(self._proceeding_from >> expectation, freeze, explain, observe)

    def new(self):
        self.expect_frozen()
        first_new = self._proceeding_from.next
        if first_new is not None:
            return self[first_new:]
        else:
            return self[self.last:self.last]

    def proceed(self):
        self.expect_frozen()
        self.new().expect_no_unobserved()
        self._proceeding_from = self.last
        self.unfreeze()

    def _expect_realized(self, expectation, occurrences, explain=True, observe=True):
        self.expect_frozen()

        occurrences = list(occurrences)
        reasons = expectation.test_until_realized(occurrences)
        if reasons is None:
            print(colors.LIGHT_RED + 'No matching ' + colors.RESET + colors.color_repr(expectation))

            # The weird always-false assert is to make pytest print occurrences nicely.
            occurrences = list(occurrences)
            assert occurrences is ('not matching expectation', expectation)

        if observe:
            self.observe(*reasons.values())

        realized_at = reasons[expectation]
        if explain:
            self._explain_how_realized(realized_at, expectation, reasons)
        return realized_at

    def expect_realized(self, expectation, explain=True, observe=True):
        return self._expect_realized(expectation, reversed(self), explain, observe)

    def expect_new(self, expectation, explain=True, observe=True):
        new = self.new()
        assert len(new) > 0, 'No new occurrences since last proceed()'
        return self._expect_realized(expectation, self.new(), explain, observe)

    def expect_not_realized(self, expectation):
        self.expect_frozen()
        assert expectation not in self

    def expect_no_new(self, expectation):
        self.expect_frozen()
        assert expectation not in self.new()

    def _explain_how_realized(self, occurrence, expectation, reasons):
        message = (
            colors.LIGHT_MAGENTA + 'Realized ' + colors.RESET +
            colors.color_repr(expectation) +
            colors.LIGHT_MAGENTA + ' via ' + colors.RESET +
            colors.color_repr(occurrence)
        )

        # For the breakdown, we want to skip the top-level expectation (since we already
        # printed that above), and also any expectations that were exact occurrences,
        # since there's no point explaining that occurrence was realized by itself.
        skip = [expectation] + [exp for exp in reasons.keys() if isinstance(exp, Occurrence)]
        for exp in skip:
            reasons.pop(exp, None)

        if reasons:
            message += colors.LIGHT_MAGENTA + ':' + colors.RESET
            for exp, reason in reasons.items():
                message += (
                    '\n    ' + colors.color_repr(exp) +
                    colors.LIGHT_MAGENTA + ' by ' + colors.RESET +
                    colors.color_repr(reason)
                )
        print(message)

    def _record(self, occurrence, block=True):
        assert isinstance(occurrence, Occurrence)
        assert occurrence.timeline is None
        assert occurrence.timestamp is None
        assert not self.is_final, 'Trying to record a new occurrence in a finalized timeline'

        self._record_queue.put(occurrence, block=block)
        if block:
            self._record_queue.join()

        return occurrence

    def _recorder_worker(self):
        while True:
            occ = self._record_queue.get()
            if occ is None:
                self._record_queue.task_done()
                break

            self._accepting_new.wait()
            with self._recorded_new:
                occ.timeline = self
                occ.timestamp = timestamp()
                occ.index = next(self._index_iter)

                if self._last is None:
                    self._beginning = occ
                    self._last = occ
                else:
                    occ.previous = self._last
                    self._last._next = occ
                    self._last = occ

                self._recorded_new.notify_all()
                self._record_queue.task_done()

    def mark(self, id, block=True):
        occ = Occurrence('Mark', id)
        occ.id = id
        occ.observed = True
        return self._record(occ, block)

    def record_request(self, command, arguments, block=True):
        occ = Occurrence('Request', command, arguments)
        occ.command = command
        occ.arguments = arguments
        occ.observed = True

        def wait_for_response(freeze=True):
            response = Response(occ, pattern.ANY).wait_until_realized(freeze)
            assert response.observed
            return response
        occ.wait_for_response = wait_for_response

        return self._record(occ, block)

    def record_response(self, request, body, block=True):
        assert isinstance(request, Occurrence)
        occ = Occurrence('Response', request, body)
        occ.request = request
        occ.body = body
        occ.success = not isinstance(occ.body, Exception)
        return self._record(occ, block)

    def record_event(self, event, body, block=True):
        occ = Occurrence('Event', event, body)
        occ.event = event
        occ.body = body
        return self._record(occ, block)

    def _snapshot(self):
        last = self._last
        occ = self._beginning
        while True:
            yield occ
            if occ is last:
                break
            occ = occ._next

    def __repr__(self):
        return '|' + ' >> '.join(repr(occ) for occ in self._snapshot()) + '|'

    def __str__(self):
        return '\n'.join(repr(occ) for occ in self._snapshot())


class Interval(tuple):
    def __new__(cls, timeline, start, stop):
        assert start is None or isinstance(start, Expectation)
        assert stop is None or isinstance(stop, Expectation)
        if not isinstance(stop, Occurrence):
            timeline.expect_frozen()

        occs = ()
        if start is None:
            start = timeline._beginning

        for occ in start.and_following(up_to=stop):
            if occ == stop:
                break
            if occ == start:
                occs = occ.and_following(up_to=stop)
                break

        result = super(Interval, cls).__new__(cls, occs)
        result.timeline = timeline
        result.start = start
        result.stop = stop
        return result

    def __contains__(self, expectation):
        return expectation.is_realized_in(self)

    def all_occurrences_of(self, expectation):
        return tuple(occ for occ in self if occ == expectation)

    def expect_no_unobserved(self):
        if not self:
            return

        # print('Checking for unobserved since %s' % colors.color_repr(self[0]))
        unobserved = [
            occ for occ in self
            if not occ.observed and all(
                exp != occ for exp in self.timeline.ignore_unobserved
            )
        ]
        if not unobserved:
            return

        print(colors.LIGHT_RED + 'Unobserved occurrences detected:' + colors.RESET)
        for occ in unobserved:
            print('   ' + colors.color_repr(occ))
        raise Exception('Unobserved occurrences detected')


class Expectation(object):
    timeline = None
    has_lower_bound = False

    def test_at(self, occurrence):
        raise NotImplementedError()

    def test_before(self, occurrence):
        return self.test_until_realized(occurrence.preceding())

    def test_at_or_before(self, occurrence):
        return self.test_until_realized(occurrence.and_preceding())

    def test_until_realized(self, occurrences):
        for occ in occurrences:
            reasons = self.test_at(occ)
            if reasons:
                return reasons
        return None

    def is_realized_at(self, occurrence):
        return self.test_at(occurrence) is not None

    def is_realized_before(self, occurrence):
        return self.test_before(occurrence) is not None

    def is_realized_at_or_before(self, occurrence):
        return self.test_at_or_before(occurrence) is not None

    def is_realized_in(self, timeline_or_interval):
        # Go in reverse on the assumption that we're more likely to be looking
        # for something that happened recently, to find it quicker.
        return self.test_until_realized(reversed(timeline_or_interval)) is not None

    def wait(self, freeze=None, explain=True):
        assert self.timeline is not None, 'Expectation must be bound to a timeline to be waited on.'
        return self.timeline.wait_for(self, freeze, explain)

    def wait_until_realized(self, freeze=None):
        return self.timeline.wait_until_realized(self, freeze)

    def __eq__(self, other):
        if self is other:
            return True
        elif isinstance(other, Occurrence) and self.is_realized_at(other):
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

    def __hash__(self):
        return hash(id(self))

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
            print(colors.RED + 'Cannot mix expectations from multiple timelines:' + colors.RESET)
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

    def test_at(self, occurrence):
        assert isinstance(occurrence, Occurrence)

        reasons = self.expectation.test_at(occurrence)
        if not reasons:
            return None

        bound_reasons = self.only_after.test_before(occurrence)
        if not bound_reasons:
            return None
        reasons.update(bound_reasons)

        reasons[self] = occurrence
        return reasons

    @property
    def has_lower_bound(self):
        return self.expectation.has_lower_bound or self.only_after.has_lower_bound

    def __repr__(self):
        return '(%r >> %r)' % (self.only_after, self.expectation)


class OrExpectation(DerivativeExpectation):
    def test_at(self, occurrence):
        assert isinstance(occurrence, Occurrence)
        for exp in self.expectations:
            reasons = exp.test_at(occurrence)
            if reasons:
                reasons[self] = occurrence
                return reasons
        return None

    def __or__(self, other):
        assert isinstance(other, Expectation)
        return OrExpectation(*(self.expectations + (other,)))

    def __repr__(self):
        return '(' + ' | '.join(repr(exp) for exp in self.expectations) + ')'


class AndExpectation(DerivativeExpectation):
    def test_at(self, occurrence):
        assert isinstance(occurrence, Occurrence)

        # At least one expectation must be realized at the occurrence.
        expectations = list(self.expectations)
        for exp in expectations:
            reasons = exp.test_at(occurrence)
            if reasons:
                break
        else:
            return None

        # And then all of the remaining expectations must have been realized
        # at or sometime before that occurrence.
        expectations.remove(exp)
        for exp in expectations:
            more_reasons = exp.test_at_or_before(occurrence)
            if not more_reasons:
                return None
            reasons.update(more_reasons)

        reasons[self] = occurrence
        return reasons

    @property
    def has_lower_bound(self):
        return any(exp.has_lower_bound for exp in self.expectations)

    def __and__(self, other):
        assert isinstance(other, Expectation)
        return AndExpectation(*(self.expectations + (other,)))

    def __repr__(self):
        return '(' + ' & '.join(repr(exp) for exp in self.expectations) + ')'


class XorExpectation(DerivativeExpectation):
    def test_at(self, occurrence):
        assert isinstance(occurrence, Occurrence)

        # At least one expectation must be realized by the occurrence.
        expectations = list(self.expectations)
        for exp in expectations:
            reasons = exp.test_at(occurrence)
            if reasons:
                break
        else:
            return None

        # And then none of the remaining expectations must have been realized
        # at or anytime before that occurrence.
        expectations.remove(exp)
        if any(exp.is_realized_at_or_before(occurrence) for exp in expectations):
            return None

        reasons[self] = occurrence
        return reasons

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

    def test_at(self, occurrence):
        assert isinstance(occurrence, Occurrence)

        if not self.condition(occurrence):
            return None

        reasons = self.expectation.test_at(occurrence)
        if not reasons:
            return None

        reasons[self] = occurrence
        return reasons

    def __repr__(self):
        return '%r?' % self.expectation


class PatternExpectation(Expectation):
    def __init__(self, *circumstances):
        self.circumstances = pattern.Pattern(circumstances)

    def test_at(self, occurrence):
        assert isinstance(occurrence, Occurrence)
        return {self: occurrence} if occurrence.circumstances == self.circumstances else None

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

    def __init__(self, *circumstances):
        assert circumstances
        self.circumstances = circumstances

        self.timeline = None
        self.timestamp = None
        self.index = None
        self.previous = None
        self._next = None
        self.observed = False

    @property
    def next(self):
        if self.timeline is None:
            return None

        with self.timeline.frozen():
            was_last = self is self.timeline.last
            occ = self._next

        if was_last:
            # The .next property of the last occurrence in a timeline can change
            # at any moment when timeline isn't frozen. So if it wasn't frozen by
            # the caller, this was an unsafe operation, and we should complain.
            self.timeline.expect_frozen()

        return occ

    def preceding(self):
        it = self.and_preceding()
        next(it)
        return it

    def and_preceding(self, up_to=None):
        assert self.timeline is not None
        assert up_to is None or isinstance(up_to, Expectation)

        if isinstance(up_to, Occurrence) and self < up_to:
            return

        occ = self
        while occ != up_to:
            yield occ
            occ = occ.previous

    def following(self):
        it = self.and_following()
        next(it)
        return it

    def and_following(self, up_to=None):
        assert self.timeline is not None
        assert up_to is None or isinstance(up_to, Expectation)
        if up_to is None:
            self.timeline.expect_frozen()

        if isinstance(up_to, Occurrence) and up_to < self:
            return

        occ = self
        while occ != up_to:
            yield occ
            occ = occ.next

    def precedes(self, occurrence):
        assert isinstance(occurrence, Occurrence)
        return any(occ is self for occ in occurrence.preceding())

    def follows(self, occurrence):
        return occurrence.precedes(self)

    def realizes(self, expectation):
        assert isinstance(expectation, Expectation)
        return expectation == self

    def test_at(self, occurrence):
        return {self: self} if occurrence is self else None

    def __lt__(self, occurrence):
        return self.precedes(occurrence)

    def __gt__(self, occurrence):
        return occurrence.precedes(self)

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
        s = '%s!%s%r' % (self.index, self.circumstances[0], self.circumstances[1:])
        if not self.observed:
            s = '*' + s
        return s
