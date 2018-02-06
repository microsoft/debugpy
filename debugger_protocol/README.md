# VSC Debugger Protocol

[Visual Studio Code](https://code.visualstudio.com/) defines several
protocols that extensions may leverage to fully integrate with VSC
features.  For ptvad the most notable of those is the debugger protocol.
When VSC handles debugger-related input via the UI, it delegates the
underlying behavior to an extension's debug adapter (e.g. ptvsd) via
the protocol.  The
[debugger_protocol](https://github.com/ericsnowcurrently/ptvsd/blob/master/debugger_protocol)
package (at which you are looking) provides resources for understanding
and using the protocol.

For more high-level info see:

* [the VSC debug protocol page](https://code.visualstudio.com/docs/extensionAPI/api-debugging)
* [the example extension page](https://code.visualstudio.com/docs/extensions/example-debuggers)


## Protocol Definition

The VSC debugger protocol has [a schema](https://github.com/Microsoft/vscode-debugadapter-node/blob/master/debugProtocol.json)
which defines its messages.  The wire format is HTTP messages with JSON
bodies.  Note that the schema does not define the semantics of the
protocol, though a large portion is elaborated in the "description"
fields in
[the schema document](https://github.com/Microsoft/vscode-debugadapter-node/blob/master/debugProtocol.json).

[//]: # (TODO: Add a link to where the wire format is defined.)


## Components

### Participants

The VSC debugger protocol involves 2 participants: the `client` and the
`debug adapter`, AKA `server`.  VSC is an example of a `client`.  ptvsd
is an example of a `debug adapter`.  VSC extensions are responsible for
providing the `debug adapter`, declaring it to VSC and connecting the
adapter to VSC when desired.

### Communication

Messages are sent back and forth over a socket.  The messages are
JSON-encoded and sent as the body of an HTTP message.

Flow:

<TBD>

### Message Types

All messages specify their `type` and a globally-unique
monotonically-increasing ID (`seq`).

The protocol consists for 3 types of messages:

* event
* request
* response

An `event` is a message by which the `debug adapter` reports to the
`client` that something happened.  Only the `debug adapter` sends
`event`s.  An `event` may be sent at any time, so the `client` may get
one after sending a `request` but before receiving the corresponding
`response`.

A `request` is a message by which the `client` requests something from
the `debug adapter` over the connection.  That "something" may be data
corresponding to the state of the debugger or it may be an action that
should be performed.  Note that the protocol dictates that the `debug
adapter` may also send `request`s to the `client`, but currently there
aren't any such `request` types.

Each `request` type has a corresponding `response` type; and for each
`request` sent by the `client`, the `debug adapter` sends back the
corresponding `response`.  `response` messages include a `request_seq`
field that matches the `seq` field of the corresponding `request`.


## Protocol-related Tools

Tools related to the schema, as well as
[a vendored copy](https://github.com/ericsnowcurrently/ptvsd/blob/master/debugger_protocol/schema/debugProtocol.json)
of the schema file itself, are found in
[debugger_protocol/schema](https://github.com/Microsoft/ptvsd/tree/master/debugger_protocol/schema).
Python bindings for the messages are found in
[debugger_protocol/messages](https://github.com/ericsnowcurrently/ptvsd/blob/master/debugger_protocol/messages).
Tools for handling the wire format are found in
[debugger_protocol/messages/wireformat.py](https://github.com/ericsnowcurrently/ptvsd/blob/master/debugger_protocol/messages/wireformat.py).

### Using the Python-implemented Message Types

The Python implementations of the schema-defined messages all share a
[ProtocolMessage](https://github.com/ericsnowcurrently/ptvsd/blob/master/debugger_protocol/messages/message.py#L27)
base class.  The 3 message types each have their own base class.  Every
message class has the following methods to aid with serialization:

* a `from_data(**raw)` factory method
* a `as_data()` method

These methods are used by
[the wireformat helpers](https://github.com/ericsnowcurrently/ptvsd/blob/master/debugger_protocol/messages/wireformat.py).


## Other Resources

* https://github.com/Microsoft/vscode-mock-debug
* https://github.com/Microsoft/vscode-debugadapter-node/tree/master/testSupport
* https://github.com/Microsoft/vscode-debugadapter-node/blob/master/protocol/src/debugProtocol.ts
* https://github.com/Microsoft/vscode-mono-debug

* http://json-schema.org/latest/json-schema-core.html
* https://python-jsonschema.readthedocs.io/
* http://python-jsonschema-objects.readthedocs.io/
