# Timeline testing

A debugpy debug session consists of the DAP ([Debug Adapter Protocol](https://microsoft.github.io/debug-adapter-protocol/specification)) requests, responses and events, which, in general, don't have any specific *absolute* ordering that can be meaningfully expected. Related requests, responses and events have *relative* ordering, and so tests for a debug session have to be able to express such ordering. For example: event E1, and either event E2 or event E3, all happened after request R was sent, but before response S to R was received.

The timeline framework, as implemented by the [timeline module](timeline.py), allows to express such tests straightforwardly in a declarative fashion in either blocking or non-blocking mode:
```py
expectation = (
    Request(R)
    >>
    (Event(E1) & (Event(E2) | Event(E3))
    >>
    Response(Request(R))
)
timeline.wait_until_realized(expectation)
assert expectation in timeline
```

## Basic terms and concepts

### Occurrence

An *occurrence* is something that occurs on a [timeline](#Timeline); it is represented by an immutable instance of `Occurrence`. An occurrence is described by its *timestamp*  (`occurrence.timestamp`) and its *circumstances* (`occurrence.circumstances`), the latter being a tuple containing everything that describes the occurrence. By convention, the first element of the tuple is a string that identifies the *kind* of occurrence, while the following elements have different meanings depending on the kind.

in a debugpy debug session as seen from the perspective of a test, the fundamental occurrences and their respective circumstances are:

- request sent: `('Request', command, arguments)`
- response received: `('Response', request, body)`
- event received: `('Event', event, body)`

(Note that debugpy itself never sends requests - it only receives and handles them.)

For a response, `body` is `MessageHandlingError(error_message)` if the request failed, and the actual body of the response if it succeeded.

There's a pseudo-occurrence called *mark*, which is never caused by debugpy itself, and exists solely so that tests can mark important points on a timeline for ordering and debugging purposes. Its circumstances are `('Mark', id)`, where `id` is an arbitrary value.

For objects representing these occurrences, named members are provided to extract individual components of `circumstances`. Thus, if it is a request, you can write `request.command` instead of `request.circumstances[1]`.

Every occurrence belongs to a specific timeline. Furthermore, every occurrence has a *preceding* occurrence (`occurrence.preceding`), except for the very first one on a timeline, for which the preceding occurrence is `None`. There is a helper method  `occurrence.backtrack()` that "walks back" from an occurrence to the beginning of the timeline, returning an iterator over `[occurrence, occurrence.preceding, occurrence.preceding.preceding, ...]`. Relative ordering can be tested with `occurrence.precedes(other)` and `occurrence.follows(other)`.

### Timeline

A *timeline* is a sequence of [occurrences](#Occurrence), in order in which they happened; it is represented by an instance of `Timeline`. Every timeline has a *beginning* (`timeline.beginning`), which is always `('Mark', 'beginning')`; thus, timelines are never empty. Every timeline also has a *last occurrence* (`timeline.last()`).

A timeline can be grown by recording new occurrences in it. This is done automatically by the test infrastructure for requests, responses and events occurring in a debug session. Marks are recorded with the `timeline.mark(id)` method, which returns the recorded mark occurrence. It is not possible to "rewrite the history" - once recorded, occurrences can never be forgotten, and do not change.

Timelines are completely thread-safe for both recording and inspection. However, because a timeline during an active debug session can grow asyncronously as new events and responses are received, it cannot be inspected directly, other than asking for the last occurrence via `timeline.last()` - which is a function rather than a property, indicating that it may return a different value on every subsequent call.

It is, however, possible to take a snapshot of a timeline via `timeline.history()`; the returned value is a list of all occurrences that were in the timeline at the point of the call, in order from first to last. This is just a shortcut for `reversed(list(timeline.last()))`.

Note that, since instances of `Occurrences` are immutable, it is safe to inspect them even as the timeline grows.

### Expectation

An *expectation* is to an [occurrence](#Occurrence) as a regex is to a string; it is represented by an instance of `Expectation`. An expectation can be *realized* at a specific occurrence. It can also be said that an expectation is realized in a [timeline](#Timeline), which means that it is realized at the last occurrence in the timeline.

Testing an occurrence against an expectation is done with `realizes`:
```py
occurrence.realizes(expectation)
```
alternatively, if we have a timeline, then operator `in` can be used to check the expectation against it:
```py
expectation in timeline     # there's some occurrence X in timeline such that X.realizes(expectation)
```
Finally, a timeline can also perform a blocking wait for an expectation to be realized with `wait_until_realized()`:
```py
t = timeline.wait_until_realized(expectation)    # blocks this thread
assert expectation in timeline
```
the return value of `wait_until_realized()` is the first occurrence that realized the expectation. If that occurrence was already in the timeline when `wait_until()` was invoked, it returns immediately.


### Basic expectations

A *basic* expectation is described by the circumstances of the occurrence the expectation is to be realized (`expectation.circumstances`). Whereas the circumstances of an occurrence is a data object, the circumstances of the expectation is usually a *pattern*, as represented by a `Some` object from the `patterns` package. An expectation is realized by an occurrence if `occurrence.circumstances == expectation.circumstances` is true (for patterns, the overloaded `==` operator is used for matching rather than equality; see the docstrings for the `patterns` package for details). For example, given a basic expectation with these circumstances:
```py
('Event', some.thing, some.dict.containing({'threadId': 1}))
```
It can be realized by any of these occurrences:
```py
('Event', 'stopped', {'reason': 'breakpoint', 'threadId': 1})
('Event', 'continued', {'threadId': 1})
```
but not by any of these:
```py
('Request', 'continue', {'threadId': 1})
('Event', 'thread', {'reason': 'exited', 'threadId': 2})
```

From this definition follows that if a basic expectation is realized at some occurrence `now`, then it is also realized at any future occurrence `later` in the same timeline such that `later.follows(now)`. Thus, once a basic expectation is realized in a timeline, it cannot be un-realized. Note that this is not necessarily true for other expectations!

Basic expectations can be created by instantiating `Expectation` directly with the desired circumstances, but it is more common to use the helper functions:
```py
Request(command, arguments)     # Expectation('Request', command, arguments)
Response(request, body)         # Expectation('Response', request, body)
Event(event, body)              # Expectation('Event', event, body)
Mark(id)                        # Expectation('Mark', id)
```

For responses, it is often desirable to specify success or failure in general, without details. This can be done by using `some.error` in the pattern:
```py
Response(request, some.error)
Response(request, ~some.error)  # success
```
Note that you don't need to do it if you specify the body of the response explicitly, since a succesful response will always have a dict as a body, and a failed response will have an exception as a body.

Since it is very common to wait for a response to a particular request, there is a shortcut to do it directly via the request occurrence:
```py
initialize_request = debug_session.send_request('initialize', {'adapterID': 'test'})
initialize_request.wait_for_response()  # timeline.wait_until(Response(initialize, ANY))
```
and a further shortcut to issue a request, wait for response, and retrieve the response body, all in a single call:
```py
initialize_response_body = debug_session.request('initialize', {'adapterID': 'test'})
```
On success, `request()` returns the body of the sucessful response directly, rather than the `Response` object. On failure, it raises the appropriate exception.

## Expectation algebra

Basic expectations can be combined together to form more complicated ones. The four basic operators on expectations are *sequencing* (`>>`), *conjunction* aka "and" (`&`), *disjunction* aka "or" (`|`), and *exclusive disjunction* aka "xor" (`^`). In addition to those, an expectation can be made *conditional*.

### Sequencing (`>>`)

When two expectations are sequenced: `(A >> B)` - the resulting expectation is realized at the occurrence at which `A` and `B` are both realized, but only if `A` was realized before `B`. For example, given an expectation:
```py
Event('stopped', ANY) >> Event('continued', ANY)
```
it will **not** be realized in a timeline:
```py
('Event', 'continued', {'threadId': 1})
('Event', 'stopped', {'reason': 'breakpoint', 'threadId': 2})
```
because "stopped" happened after "continued", and the expectation was for it to happen before. However, it will be realized in:
```py
('Event', 'continued', {'threadId': 1})
('Event', 'stopped', {'reason': 'breakpoint', 'threadId': 2})
('Event', 'thread', {'reason': 'exited', 'threadId': 1})
('Event', 'continued', {'threadId': 2})
```
Note that in this case, there is an unrelated event "thread" in between "stopped" and "continued", which does not affect the result of the operation - by the end of the timeline, both "stopped" and "continued" happened, and they did so in the requested order, so what else happened in the timeline does not affect the realization of our expectation.

Sequencing can also be done with respect to occurrences. Given occurrence `O` and expectation `X`, `(O >> X)` is an expectation that is realized at the first occurrence at which `X` is realized, and which **follows** `O` (note that it cannot be `O` itself!). For example, given:
```py
something = timeline.mark('something')
something >> Event('stopped', ANY)
```
a timeline like this:
```py
('Event', 'stopped', {'reason': 'breakpoint', 'threadId': 1})
('Mark', 'something')
```
will not realize `something`, but this one will:
```py
('Event', 'stopped', {'reason': 'breakpoint', 'threadId': 1})
('Mark', 'something')
('Event', 'stopped', {'reason': 'breakpoint', 'threadId': 2})
```

Conversely, `(X >> O)` is an expectation that is realized at the first occurrence at  which `X` is realized, and which **precedes** `O` (and, again, it cannot be `O` itself!). So:
```py
something = timeline.mark('something')
Event('stopped', ANY) >> something
```
will be realized at `something`, but only if the timeline already had an event "stopped" at that moment - since timelines only grow into the future, it is impossible for an event necessary to realize this expectation to appear after `mark()` was invoked.

In practice, this is most often used with requests and responses; for example, to describe an event that should occur between a specific request and its response:
```py
initialize = debug_session.send_request('initialize', {'adapterID': 'test'})
initialize_response = initialize_request.wait_for_response()
assert (
    initialize
    >>
    Event('initialized', {})
    >>
    initialize_response
) in debug_session.timeline
```
Another useful pattern is `>>` combined with `wait_until`:
```
initialize = debug_session.send_request('initialize', {'adapterID': 'test'})
initialized = debug_session.wait_until(Event('initialized'))
assert (
    initialize
    >>
    Event('output', some.dict.containing({'category': 'telemetry'}))
    >>
    initialized
) in debug_session.timeline
```

### Conjuction (`&`)

When two expectations are conjuncted: `(A & B)` - the resulting expectation is realized at the occurrence at which `A` and `B` are both realized, regardless of their relative order. Thus:
```py
Event('stopped', some.thing) & Event('continued', some.thing)
```
this expectation will be realized in timeline:
```py
('Event', 'continued', {'threadId': 1})
('Event', 'thread', {'reason': 'exited', 'threadId': 1})
('Event', 'stopped', {'reason': 'breakpoint', 'threadId': 2})
```
but also in a differently ordered timeline:
```py
('Event', 'stopped', {'reason': 'breakpoint', 'threadId': 2})
('Event', 'continued', {'threadId': 1})
('Event', 'thread', {'reason': 'exited', 'threadId': 1})
```
This is most commonly used as seen above, with related events where their relative ordering is unspecified (usually also framed by `>>` to narrow it down to a specific request/response pair). It can also be used to concurrently send multiple requests, and wait until they all got their responses:
```py
pause1 = debug_session.send_request('pause', {'threadId': '1'})
pause2 = debug_session.send_request('pause', {'threadId': '2'})
debug_session.wait_until_realized(Response(pause1) & Response(pause2))
```

### Disjunction (`|`)

When two expectations are disjuncted: `(A | B)` - the resulting expectation is realized at the first occurrence at which either `A` or `B` is realized, or both are realized. Thus, the expectation:
```py
Event('stopped', some.thing) | Event('continued', some.thing)
```
will be realized in any of these timelines:
```py
('Event', 'continued', {'threadId': 1})
('Event', 'thread', {'reason': 'exited', 'threadId': 1})

('Event', 'stopped', {'reason': 'breakpoint', 'threadId': 2})

('Event', 'continued', {'threadId': 1})
('Event', 'thread', {'reason': 'exited', 'threadId': 1})
('Event', 'stopped', {'reason': 'breakpoint', 'threadId': 2})

('Event', 'thread', {'reason': 'exited', 'threadId': 1})
('Event', 'stopped', {'reason': 'breakpoint', 'threadId': 2})
('Event', 'continued', {'threadId': 1})
```

It is usually used to concurrently send multiple requests, and wait until the first one gets a response:
```py
pause1 = debug_session.send_request('pause', {'threadId': '1'})
pause2 = debug_session.send_request('pause', {'threadId': '2'})
pause_response = debug_session.wait_until_realized(Response(pause1) | Response(pause2))
handled_request = pause_response.request
if handled_request is pause1:
    ...
```

### Exclusive disjuction (`^`)

When two expectations are exclusively disjuncted: `(A ^ B)` - the resulting expectation is realized at the first occurrence at which either `A` or `B` is realized, but not both. Thus, the expectation:
```py
Event('stopped', ANY) ^ Event('continued', ANY)
```
is realized in:
```py
('Event', 'continued', {'threadId': 1})
('Event', 'thread', {'reason': 'exited', 'threadId': 1})

('Event', 'thread', {'reason': 'exited', 'threadId': 1})
('Event', 'stopped', {'reason': 'breakpoint', 'threadId': 2})
```
but not in:
```py
('Event', 'continued', {'threadId': 1})
('Event', 'thread', {'reason': 'exited', 'threadId': 1})
('Event', 'stopped', {'reason': 'breakpoint', 'threadId': 2})
```
This can be used, for example, to test a request that can produce different events depending on various conditions, but should never produce both at the same time.

### Conditional expectation

Given an expectation `X`, a conditional expectation `X.when(condition)` is realized at the occurrence `O` at which `X` is realized, but only if `condition(O)` returns `True`. In practice, it is typically used with a lambda to check for events that are caused by requests, but only happen when a request is successful, e.g.:
```
initialize_request = debug_session.send_request('initialize', {'adapterID': 'test'}).wait_for_response()
assert Event('initialized', {}).when(
    lambda occ: Response(initialize_request, SUCCESS) in occ.timeline
) in debug_session.timeline
```

## Debug session

A debug session runs debugpy, and records requests, responses and events on a timeline as they occur. It is an instance of `tests.debug.Session`. A test normally creates an instance in a `with`-statement to ensure proper cleanup:
```py
def test_run():
    with debug.Session() as debug_session:
        ...
```

The timeline is exposed as `debug_session.timeline`. In addition to that, a number of common timeline methods are exposed directly on the session object.

A freshly obtained session is dormant - there's no debugpy running, and nothing to record. To make it useful, it needs to be primed with a *target* to run some code:
```py
with debug_session.launch(targets.Program('example.py')):
   ...
```

Inside the with-statement, debugpy is spun up and connected to the test process, and the initial handshake sequence ("initialize" request/response) has been performed. The timeline is also live, containing the recording of the handshake, and waiting for further occurrences. However, the debugger is still idle - the script or module we specified isn't actually running yet. This is a good time to adjust debug configuration, and to issue requests to set any breakpoints:
```py
with debug_session.launch(targets.Program('example.py')):
    debug_session.config['redirectOutput]' = True
    debug_session.request('setBreakpoints', [
        {
            'source': {'path': 'example.py'},
            'breakpoints': [{'line': 3}, {'line': 5}]
        }
    ])
```
Once the with-statement exits, a "launch" or "attach" request with the appropriate configuration is issued, and actual debugging begins.
