# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

from __future__ import absolute_import, division, print_function, unicode_literals

import collections
import contextlib
import itertools
import threading

from debugpy.common import compat, fmt, log, messaging, timestamp
from debugpy.common.compat import queue

from tests.patterns import some


SINGLE_LINE_REPR_LIMIT = 120
"""If repr() of an expectation or an occurrence is longer than this value, it will
be formatted to use multiple shorter lines if possible.
"""

# For use by Expectation.__repr__. Uses fmt() to create unique instances.
_INDENT = fmt("{0}", "_INDENT")
_DEDENT = fmt("{0}", "_DEDENT")


class Timeline(object):
    def __init__(self, name=None):
        self.name = str(name if name is not None else id(self))
        self.ignore_unobserved = []

        self._listeners = []  # [(expectation, callable)]
        self._index_iter = itertools.count(1)
        self._accepting_new = threading.Event()
        self._finalized = threading.Event()
        self._recorded_new = threading.Condition()
        self._record_queue = queue.Queue()

        self._recorder_thread = threading.Thread(
            target=self._recorder_worker, name=fmt("{0} recorder", self)
        )
        self._recorder_thread.daemon = True
        self._recorder_thread.start()

        # Set up initial environment for our first mark()
        self._last = None
        self._beginning = None
        self._accepting_new.set()

        self._beginning = self.mark("START")
        assert self._last is self._beginning
        self._proceeding_from = self._beginning

    def expect_frozen(self):
        if not self.is_frozen:
            raise Exception("Timeline can only be inspected while frozen.")

    def __iter__(self):
        self.expect_frozen()
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
        return any(expectation.test(self.beginning, self.last))

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

        log.info("Finalizing timeline...")
        with self.unfrozen():
            self.mark("FINISH")

        with self.unfrozen():
            self._finalized.set()
            # Drain the record queue.
            self._record_queue.join()
            # Tell the recorder to shut itself down.
            self._record_queue.put(None)
            self._recorder_thread.join()

        assert self._record_queue.empty(), "Finalized timeline had pending records"

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

    def observe_all(self, expectation=None):
        self.expect_frozen()
        occs = (
            list(self)
            if expectation is None
            else [occ for occ in self if occ == expectation]
        )
        self.observe(*occs)

    def wait_until(self, condition, freeze=None):
        freeze = freeze or self.is_frozen
        try:
            with self._recorded_new:
                # First, test the condition against the timeline as it currently is.
                with self.frozen():
                    result = condition()
                    if result:
                        return result

                # Now keep spinning waiting for new occurrences to come, and test the
                # condition against every new batch in turn.
                self.unfreeze()
                while True:
                    self._recorded_new.wait()
                    with self.frozen():
                        result = condition()
                        if result:
                            return result
                    assert not self.is_final

        finally:
            if freeze:
                self.freeze()

    def _wait_until_realized(
        self, expectation, freeze=None, explain=True, observe=True
    ):
        def has_been_realized():
            for reasons in expectation.test(self.beginning, self.last):
                if observe:
                    self.expect_realized(expectation, explain=explain, observe=observe)
                return reasons

        reasons = self.wait_until(has_been_realized, freeze)
        return latest_of(reasons.values())

    def wait_until_realized(self, expectation, freeze=None, explain=True, observe=True):
        if explain:
            log.info("Waiting for {0!r}", expectation)
        return self._wait_until_realized(expectation, freeze, explain, observe)

    def wait_for(self, expectation, freeze=None, explain=True):
        assert expectation.has_lower_bound, (
            "Expectation must have a lower time bound to be used with wait_for()! "
            "Use >> to sequence an expectation against an occurrence to establish a lower bound, "
            "or wait_for_next() to wait for the next expectation since the timeline was last "
            "frozen, or wait_until_realized() when a lower bound is really not necessary."
        )
        if explain:
            log.info("Waiting for {0!r}", expectation)
        return self._wait_until_realized(expectation, freeze, explain=explain)

    def wait_for_next(self, expectation, freeze=True, explain=True, observe=True):
        if explain:
            log.info("Waiting for next {0!r}", expectation)
        return self._wait_until_realized(
            self._proceeding_from >> expectation, freeze, explain, observe
        )

    def new(self):
        self.expect_frozen()
        first_new = self._proceeding_from.next
        if first_new is not None:
            return self[first_new:]
        else:
            return self[self.last : self.last]

    def proceed(self):
        self.expect_frozen()
        self.new().expect_no_unobserved()
        self._proceeding_from = self.last
        self.unfreeze()

    def _expect_realized(self, expectation, first, explain=True, observe=True):
        self.expect_frozen()

        try:
            reasons = next(expectation.test(first, self.last))
        except StopIteration:
            log.info("No matching {0!r}", expectation)
            occurrences = list(first.and_following())
            log.info("Occurrences considered: {0!r}", occurrences)
            raise AssertionError("Expectation not matched")

        occs = tuple(reasons.values())
        assert occs
        if observe:
            self.observe(*occs)
        if explain:
            self._explain_how_realized(expectation, reasons)
        return occs if len(occs) > 1 else occs[0]

    def expect_realized(self, expectation, explain=True, observe=True):
        return self._expect_realized(expectation, self.beginning, explain, observe)

    def expect_new(self, expectation, explain=True, observe=True):
        assert (
            self._proceeding_from.next is not None
        ), "No new occurrences since last proceed()"
        return self._expect_realized(
            expectation, self._proceeding_from.next, explain, observe
        )

    def expect_not_realized(self, expectation):
        self.expect_frozen()
        assert expectation not in self

    def expect_no_new(self, expectation):
        self.expect_frozen()
        assert expectation not in self.new()

    def _explain_how_realized(self, expectation, reasons):
        message = fmt("Realized {0!r}", expectation)

        # For the breakdown, we want to skip any expectations that were exact occurrences,
        # since there's no point explaining that occurrence was realized by itself.
        skip = [exp for exp in reasons.keys() if isinstance(exp, Occurrence)]
        for exp in skip:
            reasons.pop(exp, None)

        if reasons == {expectation: some.object}:
            # If there's only one expectation left to explain, and it's the top-level
            # one, then we have already printed it, so just add the explanation.
            reason = reasons[expectation]
            if "\n" in message:
                message += fmt(" == {0!r}", reason)
            else:
                message += fmt("\n      == {0!r}", reason)
        elif reasons:
            # Otherwise, break it down expectation by expectation.
            message += ":"
            for exp, reason in reasons.items():
                message += fmt("\n\n   where {0!r}\n      == {1!r}", exp, reason)
        else:
            message += "."

        log.info("{0}", message)

    def _record(self, occurrence, block=True):
        assert isinstance(occurrence, Occurrence)
        assert occurrence.timeline is None
        assert occurrence.timestamp is None
        assert (
            not self.is_final
        ), "Trying to record a new occurrence in a finalized timeline"

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
                occ.timestamp = timestamp.current()
                occ.index = next(self._index_iter)

                if self._last is None:
                    self._beginning = occ
                    self._last = occ
                else:
                    assert self._last.timestamp <= occ.timestamp
                    occ.previous = self._last
                    self._last._next = occ
                    self._last = occ

                self._recorded_new.notify_all()
                self._record_queue.task_done()

                for exp, callback in tuple(self._listeners):
                    if exp == occ:
                        callback(occ)

    def mark(self, id, block=True):
        occ = Occurrence("mark", id)
        occ.id = id
        occ.observed = True
        return self._record(occ, block)

    def record_event(self, message, block=True):
        occ = EventOccurrence(message)
        return self._record(occ, block)

    def record_request(self, message, block=True):
        occ = RequestOccurrence(message)
        occ.observed = True
        return self._record(occ, block)

    def record_response(self, request_occ, message, block=True):
        occ = ResponseOccurrence(request_occ, message)
        return self._record(occ, block)

    def when(self, expectation, callback):
        """For every occurrence recorded after this call, invokes callback(occurrence)
        if occurrence == expectation.
        """
        self._listeners.append((expectation, callback))

    def _snapshot(self):
        last = self._last
        occ = self._beginning
        while True:
            yield occ
            if occ is last:
                break
            occ = occ._next

    def __repr__(self):
        return "|" + " >> ".join(repr(occ) for occ in self._snapshot()) + "|"

    def __str__(self):
        return "Timeline-" + self.name


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
        return any(expectation.test(self[0], self[-1])) if len(self) > 0 else False

    def all_occurrences_of(self, expectation):
        return tuple(occ for occ in self if occ == expectation)

    def expect_no_unobserved(self):
        if not self:
            return

        unobserved = [
            occ
            for occ in self
            if not occ.observed
            and all(exp != occ for exp in self.timeline.ignore_unobserved)
        ]
        if not unobserved:
            return

        raise log.error(
            "Unobserved occurrences detected:\n\n{0}\n\nignoring unobserved:\n\n{1}",
            "\n\n".join(repr(occ) for occ in unobserved),
            "\n\n".join(repr(exp) for exp in self.timeline.ignore_unobserved),
        )


class Expectation(object):
    timeline = None
    has_lower_bound = False

    def test(self, first, last):
        raise NotImplementedError()

    def wait(self, freeze=None, explain=True):
        assert (
            self.timeline is not None
        ), "Expectation must be bound to a timeline to be waited on."
        return self.timeline.wait_for(self, freeze, explain)

    def wait_until_realized(self, freeze=None):
        return self.timeline.wait_until_realized(self, freeze)

    def __eq__(self, other):
        if self is other:
            return True
        elif isinstance(other, Occurrence) and any(self.test(other, other)):
            return True
        else:
            return NotImplemented

    def __ne__(self, other):
        return not self == other

    def after(self, other):
        return SequencedExpectation(other, self)

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
        raise NotImplementedError


class DerivativeExpectation(Expectation):
    def __init__(self, *expectations):
        self.expectations = expectations
        assert len(expectations) > 0
        assert all(isinstance(exp, Expectation) for exp in expectations)

        timelines = {id(exp.timeline): exp.timeline for exp in expectations}
        timelines.pop(id(None), None)
        if len(timelines) > 1:
            offending_expectations = ""
            for tl_id, tl in timelines.items():
                offending_expectations += fmt("\n    {0}: {1!r}\n", tl_id, tl)
            raise log.error(
                "Cannot mix expectations from multiple timelines:\n{0}",
                offending_expectations,
            )
        for tl in timelines.values():
            self.timeline = tl

    @property
    def has_lower_bound(self):
        return all(exp.has_lower_bound for exp in self.expectations)

    def flatten(self):
        """Flattens nested expectation chains.

        If self is of type E, and given an expectation like::

            E(E(e1, E(e2, e3)), E(E(e4, e5), E(e6)))

        flatten() produces an iterator over::

            e1, e2, e3, e4, e5, e6
        """
        for exp in self.expectations:
            if type(exp) is type(self):
                for exp in exp.flatten():
                    yield exp
            else:
                yield exp

    def describe(self, newline):
        """Returns an iterator describing this expectation. This method is used
        to implement repr().

        For every yielded _INDENT and _DEDENT, a newline and the appropriate amount
        of spaces for correct indentation at the current level is added to the repr.

        For every yielded Expectation, describe() is invoked recursively.

        For every other yielded value, str(value) added to the repr.

        newline is set to either "" or "\n", depending on whether the repr must be
        single-line or multiline. Implementations of describe() should use it in
        lieu of raw "\n" insofar as possible; however, repr() will automatically
        fall back to multiline mode if "\n" occurs in single-line mode.

        The default implementation produces a description that looks like::

            (e1 OP e2 OP e3 OP ...)

        where OP is the value of self.OPERATOR.
        """
        op = self.OPERATOR

        yield "("
        yield _INDENT

        first = True
        for exp in self.flatten():
            if first:
                first = False
            else:
                yield " " + op + " "
                yield newline
            yield exp

        yield _DEDENT
        yield ")"

    def __repr__(self):
        def indent():
            return indent.level * "    " if newline else ""

        def recurse(exp):
            for item in exp.describe(newline):
                if isinstance(item, DerivativeExpectation):
                    recurse(item)
                elif item is _INDENT:
                    indent.level += 1
                    result.append(newline + indent())
                elif item is _DEDENT:
                    assert indent.level > 0, "_DEDENT without matching _INDENT"
                    indent.level -= 1
                    result.append(newline + indent())
                else:
                    item = str(item).replace("\n", "\n" + indent())
                    result.append(item)

        # Try single-line repr first.
        indent.level = 0
        newline = ""
        result = []
        recurse(self)
        s = "".join(result)
        if len(s) <= SINGLE_LINE_REPR_LIMIT and "\n" not in s:
            return s

        # If it was too long, or had newlines anyway, fall back to multiline.
        assert indent.level == 0
        newline = "\n"
        result[:] = []
        recurse(self)
        return "".join(result)


class SequencedExpectation(DerivativeExpectation):
    OPERATOR = ">>"

    def __init__(self, first, second):
        super(SequencedExpectation, self).__init__(first, second)

    @property
    def first(self):
        return self.expectations[0]

    @property
    def second(self):
        return self.expectations[1]

    def test(self, first, last):
        assert isinstance(first, Occurrence)
        assert isinstance(last, Occurrence)

        for first_reasons in self.first.test(first, last):
            first_occs = first_reasons.values()
            lower_bound = latest_of(first_occs).next
            if lower_bound is not None:
                for second_reasons in self.second.test(lower_bound, last):
                    reasons = second_reasons.copy()
                    reasons.update(first_reasons)
                    yield reasons

    @property
    def has_lower_bound(self):
        return self.first.has_lower_bound or self.second.has_lower_bound


class OrExpectation(DerivativeExpectation):
    OPERATOR = "|"

    def test(self, first, last):
        assert isinstance(first, Occurrence)
        assert isinstance(last, Occurrence)

        for exp in self.expectations:
            for reasons in exp.test(first, last):
                yield reasons

    def __or__(self, other):
        assert isinstance(other, Expectation)
        return OrExpectation(*(self.expectations + (other,)))


class AndExpectation(DerivativeExpectation):
    OPERATOR = "&"

    def test(self, first, last):
        assert isinstance(first, Occurrence)
        assert isinstance(last, Occurrence)

        if len(self.expectations) <= 1:
            for exp in self.expectations:
                for reasons in exp.test(first, last):
                    yield reasons
            return

        lhs = self.expectations[0]
        rhs = AndExpectation(*self.expectations[1:])
        for lhs_reasons in lhs.test(first, last):
            for rhs_reasons in rhs.test(first, last):
                reasons = lhs_reasons.copy()
                reasons.update(rhs_reasons)
                yield reasons

    @property
    def has_lower_bound(self):
        return any(exp.has_lower_bound for exp in self.expectations)

    def __and__(self, other):
        assert isinstance(other, Expectation)
        return AndExpectation(*(self.expectations + (other,)))

    def __repr__(self):
        return "(" + " & ".join(repr(exp) for exp in self.expectations) + ")"


class XorExpectation(DerivativeExpectation):
    OPERATOR = "^"

    def test(self, first, last):
        assert isinstance(first, Occurrence)
        assert isinstance(last, Occurrence)

        reasons = None
        for exp in self.expectations:
            for exp_reasons in exp.test(first, last):
                if reasons is None:
                    reasons = exp_reasons
                else:
                    return

        if reasons is not None:
            yield reasons

    @property
    def has_lower_bound(self):
        return all(exp.has_lower_bound for exp in self.expectations)

    def __xor__(self, other):
        assert isinstance(other, Expectation)
        return XorExpectation(*(self.expectations + (other,)))


class ConditionalExpectation(DerivativeExpectation):
    def __init__(self, expectation, condition):
        self.condition = condition
        super(ConditionalExpectation, self).__init__(expectation)

    @property
    def expectation(self):
        return self.expectations[0]

    def test(self, first, last):
        assert isinstance(first, Occurrence)
        assert isinstance(last, Occurrence)

        for reasons in self.expectation.test(first, last):
            occs = reasons.values()
            if self.condition(*occs):
                yield reasons

    def describe(self, newline):
        yield "?"
        yield self.expectation


class PatternExpectation(Expectation):
    def __init__(self, *circumstances):
        self.circumstances = circumstances

    def test(self, first, last):
        assert isinstance(first, Occurrence)
        assert isinstance(last, Occurrence)

        for occ in first.and_following(up_to=last, inclusive=True):
            if occ.circumstances == self.circumstances:
                yield {self: occ}

    def describe(self):
        rest = repr(self.circumstances[1:])
        if rest.endswith(",)"):
            rest = rest[:-2] + ")"
        return fmt("<{0}{1}>", self.circumstances[0], rest)

    def __repr__(self):
        return self.describe()


def Mark(id):
    return PatternExpectation("mark", id)


def _describe_message(message_type, *items):
    items = (("type", message_type),) + items
    d = collections.OrderedDict(items)

    # Keep it all on one line if it's short enough, but indent longer ones.
    for format_string in "{0!j:indent=None}", "{0!j}":
        s = fmt(format_string, d)
        s = "{..., " + s[1:]

        # Used by some.dict.containing to inject ... as needed.
        s = s.replace('"\\u0002...": "...\\u0003"', "...")
        # Used by some.* and by Event/Request/Response expectations below.
        s = s.replace('"\\u0002', "")
        s = s.replace('\\u0003"', "")

        if len(s) <= SINGLE_LINE_REPR_LIMIT:
            break

    return s


def Event(event, body=some.object):
    exp = PatternExpectation("event", event, body)
    items = (("event", event),)
    if body is some.object:
        items += (("\002...", "...\003"),)
    else:
        items += (("body", body),)
    exp.describe = lambda: _describe_message("event", *items)
    return exp


def Request(command, arguments=some.object):
    exp = PatternExpectation("request", command, arguments)
    items = (("command", command),)
    if arguments is some.object:
        items += (("\002...", "...\003"),)
    else:
        items += (("arguments", arguments),)
    exp.describe = lambda: _describe_message("request", *items)
    return exp


def Response(request, body=some.object):
    assert isinstance(request, Expectation) or isinstance(request, RequestOccurrence)

    exp = PatternExpectation("response", request, body)
    exp.timeline = request.timeline
    exp.has_lower_bound = request.has_lower_bound

    # Try to be as specific as possible.
    if isinstance(request, Expectation):
        if request.circumstances[0] != "request":
            exp.describe = lambda: fmt("response to {0!r}", request)
            return
        else:
            items = (("command", request.circumstances[1]),)
    else:
        items = (("command", request.command),)

    if isinstance(request, Occurrence):
        items += (("request_seq", request.seq),)

    if body is some.object:
        items += (("\002...", "...\003"),)
    elif body is some.error or body == some.error:
        items += (("success", False),)
        if body == some.error:
            items += (("message", compat.force_str(body)),)
    else:
        items += (("body", body),)

    exp.describe = lambda: _describe_message("response", *items)
    return exp


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

    def and_preceding(self, up_to=None, inclusive=False):
        assert self.timeline is not None
        assert up_to is None or isinstance(up_to, Expectation)

        if isinstance(up_to, Occurrence) and self < up_to:
            return

        occ = self
        while occ != up_to:
            yield occ
            occ = occ.previous

        if inclusive:
            yield occ

    def following(self):
        it = self.and_following()
        next(it)
        return it

    def and_following(self, up_to=None, inclusive=False):
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

        if inclusive:
            yield occ

    def precedes(self, occurrence):
        assert isinstance(occurrence, Occurrence)
        return any(occ is self for occ in occurrence.preceding())

    def follows(self, occurrence):
        return occurrence.precedes(self)

    def realizes(self, expectation):
        assert isinstance(expectation, Expectation)
        return expectation == self

    def test(self, first, last):
        assert isinstance(first, Occurrence)
        assert isinstance(last, Occurrence)

        for occ in first.and_following(up_to=last, inclusive=True):
            if occ is self:
                yield {self: self}

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

    def __repr__(self):
        return fmt(
            "{2}{0}.{1}",
            self.index,
            self.describe_circumstances(),
            "" if self.observed else "*",
        )

    def describe_circumstances(self):
        rest = repr(self.circumstances[1:])
        if rest.endswith(",)"):
            rest = rest[:-2] + ")"
        return fmt("{0}{1}", self.circumstances[0], rest)


class MessageOccurrence(Occurrence):
    """An occurrence representing a DAP message (event, request, or response).

    Its circumstances == (self.TYPE, self._key, self._data).
    """

    TYPE = None
    """Used for self.circumstances[0].

    Must be defined by subclasses.
    """

    def __init__(self, message):
        assert self.TYPE
        assert isinstance(message, messaging.Message)

        # Assign message first for the benefit of self._data in child classes.
        self.message = message
        super(MessageOccurrence, self).__init__(self.TYPE, self._key, self._data)

    @property
    def seq(self):
        return self.message.seq

    @property
    def _key(self):
        """The part of the message that describes it in general terms - e.g. for
        an event, it's the name of the event.
        """
        raise NotImplementedError

    @property
    def _data(self):
        """The part of the message that is used for matching expectations, excluding
        self._key.
        """
        raise NotImplementedError

    @property
    def _id(self):
        """The part of the message that is necessary and sufficient to uniquely
        identify it. Used for __repr__().

        Must be an ordered list of key-value tuples, suitable for OrderedDict().
        """
        return [("seq", self.message.seq), ("type", self.TYPE)]

    def __call__(self, *args, **kwargs):
        return self.message(*args, **kwargs)

    def describe_circumstances(self):
        id = collections.OrderedDict(self._id)

        # Keep it all on one line if it's short enough, but indent longer ones.
        s = fmt("{0!j:indent=None}", id)
        if len(s) > SINGLE_LINE_REPR_LIMIT:
            s = fmt("{0!j}", id)
        return s

    # For messages, we don't want to include their index, because they already have
    # "seq" to identify them uniquely, and including both is confusing.
    def __repr__(self):
        return ("" if self.observed else "*") + self.describe_circumstances()


class EventOccurrence(MessageOccurrence):
    TYPE = "event"

    def __init__(self, message):
        assert isinstance(message, messaging.Event)
        super(EventOccurrence, self).__init__(message)

    @property
    def event(self):
        return self.message.event

    @property
    def body(self):
        return self.message.body

    @property
    def _key(self):
        return self.event

    @property
    def _data(self):
        return self.body

    @property
    def _id(self):
        return super(EventOccurrence, self)._id + [("event", self.message.event)]


class RequestOccurrence(MessageOccurrence):
    TYPE = "request"

    def __init__(self, message):
        assert isinstance(message, messaging.Request)
        super(RequestOccurrence, self).__init__(message)
        self.response = None
        if isinstance(message, messaging.OutgoingRequest):
            self.on_response = message.on_response

    @property
    def command(self):
        return self.message.command

    @property
    def arguments(self):
        return self.message.arguments

    @property
    def _key(self):
        return self.command

    @property
    def _data(self):
        return self.arguments

    @property
    def _id(self):
        return super(RequestOccurrence, self)._id + [("command", self.message.command)]

    def wait_for_response(self, freeze=True, raise_if_failed=True):
        response = Response(self, some.object).wait_until_realized(freeze)
        assert response.observed
        if raise_if_failed and not response.success:
            raise response.body
        else:
            return response


class ResponseOccurrence(MessageOccurrence):
    TYPE = "response"

    def __init__(self, request_occ, message):
        assert isinstance(request_occ, RequestOccurrence)
        assert isinstance(message, messaging.Response)

        # Assign request first for the benefit of self._key.
        self.request = request_occ
        request_occ.response = self
        super(ResponseOccurrence, self).__init__(message)

    @property
    def body(self):
        return self.message.body

    @property
    def result(self):
        return self.message.result

    @property
    def success(self):
        return self.message.success

    @property
    def _key(self):
        return self.request

    @property
    def _data(self):
        return self.body

    @property
    def _id(self):
        return super(ResponseOccurrence, self)._id + [
            ("command", self.message.request.command),
            ("request_seq", self.message.request.seq),
        ]

    def causing(self, *expectations):
        for exp in expectations:
            (self >> exp).wait()
        return self


def earliest_of(occurrences):
    return min(occurrences, key=lambda occ: occ.index)


def latest_of(occurrences):
    return max(occurrences, key=lambda occ: occ.index)
