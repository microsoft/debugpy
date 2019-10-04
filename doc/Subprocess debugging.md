# Subprocess debugging

## Terminology

_Debuggee process_ - the process that is being debugged.

_IDE_ - VSCode or other DAP client.

_Debug server_ - pydevd with ptvsd wrapper; hosted inside the debuggee process,
one for each.

_Debug adapter_ - ptvsd adapter that mediates between IDE and server.

_IDE listener port_ - port opened by the adapter, on which it listens for incoming
connections from the IDE.

_Server listener port_ - port opened by the adapter, on which it listens for incoming
connections from the servers.

_Adapter listener port_ - port opened by the server, on which it listens for incoming
connection from the adapter.



## "launch" scenario

1. User starts debugging (F5) with "launch" debug config.
1. User code spawns child process.
1. User stops debugging.

```mermaid
sequenceDiagram
# Install "GitHub + Mermaid" from the Chrome Web Store to render the diagram

participant IDE
participant Adapter
participant Debuggee_1
participant Debuggee_2


Note left of IDE: user starts<br/>debugging

IDE ->> Adapter: spawn and connect over stdio

IDE ->>+ Adapter: request "launch"

Adapter ->>+ Debuggee_1: spawn and pass server listener port (cmdline)

Debuggee_1 -->>- Adapter: connect to server listener port

Adapter ->>+ Debuggee_1: request "initialize", "launch"

Debuggee_1 -->>- Adapter: respond to "initialize", "launch"

Debuggee_1 ->>+ Debuggee_1: start debug session

Adapter -->>- IDE: respond to "launch"

loop every message between IDE and Debuggee_1
Note over IDE,Debuggee_1: propagate message
end


Note right of Debuggee_1: user code spawns<br/>child process

Debuggee_1 ->>+ Debuggee_2: spawn and pass server listener port (cmdline)

Debuggee_2 ->>- Adapter: connect to server listener port

Adapter ->>+ Debuggee_2: request "pydevd_systemInfo"

Debuggee_2 -->>- Adapter: respond to "pydevd_systemInfo"

Adapter ->>+ IDE: "ptvsd_subprocess" event:

IDE ->>- Adapter: connect to IDE listener port

IDE ->>+ Adapter: request "attach" to Debuggee_2

Adapter ->>+ Debuggee_2: request "initialize", "attach"

Debuggee_2 -->>- Adapter: respond to "initialize", "attach"

Debuggee_2 ->>+ Debuggee_2: start debug session

Adapter -->>- IDE: respond to "attach"

loop every message between IDE and Debuggee_2
Note over IDE,Debuggee_2: propagate message
end


Note left of IDE: user stops debugging

IDE ->>+ Adapter: request "disconnect" from Debuggee_2

Adapter ->> Debuggee_2: request "disconnect"

Debuggee_2 ->> Adapter: confirm "disconnect"

Note over Adapter,Debuggee_2: TCP connection is maintained

Adapter -->>- IDE: confirm "disconnect" from Debuggee_2

IDE -X+ Adapter: request "disconnect" from Debuggee_1

Note over Adapter: implies "terminate"

Adapter -X+ Debuggee_1: request "terminate"

Debuggee_1 -X Debuggee_2: kill process
deactivate Debuggee_2

Debuggee_1 -->>- Adapter: confirm "terminate"

Debuggee_1 -X- Debuggee_1: exits

Adapter -->>- IDE: confirm "disconnect" from Debuggee_1

Adapter -X Adapter: exits
```



## "attach" scenario

1. User starts debuggee process with debug server in it (ptvsd command line or `ptvsd.enable_attach()`).
1. User starts debugging (F5) with "attach" debug config.
1. User code spawns child process.
1. User disconnects from debuggee.
1. User reconnects to debuggee.

```mermaid
sequenceDiagram
# Install "GitHub + Mermaid" from the Chrome Web Store to render the diagram

participant IDE
participant Adapter
participant Debuggee_1
participant Debuggee_2


Note left of Debuggee_1: user spawns<br/>debuggee

Debuggee_1 ->>+ Adapter: spawn and pass adapter listener port (cmdline)

Adapter -->>- Debuggee_1: connect to adapter listener port

Adapter ->> Debuggee_1: request "setDebuggerProperty" for server listener port


Note left of IDE: user starts<br/>debugging

IDE ->> Adapter: connect to IDE listener port

IDE ->>+ Adapter: request "attach"

Adapter ->>+ Debuggee_1: request "initialize", "attach"

Debuggee_1 -->>- Adapter: respond to "initialize", "attach"

Debuggee_1 ->>+ Debuggee_1: start debug session

Adapter -->>- IDE: respond to "attach"

loop every message between IDE and Debuggee_1
Note over IDE,Debuggee_1: propagate message
end


Note right of Debuggee_1: user code spawns<br/>child process

Debuggee_1 ->>+ Debuggee_2: spawn and pass server listener port (cmdline)

Debuggee_2 ->>- Adapter: connect to server listener port

Adapter ->>+ Debuggee_2: request "pydevd_systemInfo"

Debuggee_2 -->>- Adapter: respond to "pydevd_systemInfo"

Adapter ->>+ IDE: "ptvsd_subprocess" event

IDE ->>- Adapter: connect to IDE listener port

IDE ->>+ Adapter: request "attach" to Debuggee_2

Adapter ->>+ Debuggee_2: request "initialize", "attach"

Debuggee_2 -->>- Adapter: respond to "initialize", "attach"

Debuggee_2 ->>+ Debuggee_2: start debug session

Adapter -->>- IDE: respond to "attach"

loop every message between IDE and Debuggee_2
Note over IDE,Debuggee_2: propagate message
end


Note left of IDE: user detaches IDE

IDE ->>+ Adapter: request "disconnect" from Debuggee_2

Adapter ->>+ Debuggee_2: request "disconnect"

Debuggee_2 ->>- Adapter: confirm "disconnect"

Debuggee_2 ->>- Debuggee_2: end debug session

Note over Adapter,Debuggee_2: TCP connection is maintained

Adapter -->>- IDE: confirm "disconnect" from Debuggee_2

IDE ->>+ Adapter: request "disconnect" from Debuggee_1

Adapter ->>+ Debuggee_1: request "disconnect"

Debuggee_1 ->>- Adapter: confirm "disconnect"

Debuggee_1 ->>- Debuggee_1: end debug session

Note over Adapter,Debuggee_1: TCP connection is maintained

Adapter -->>- IDE: confirm "disconnect" from Debuggee_1

Note over Adapter: continues running



Note left of IDE: User re-attaches IDE<br/>(same host/port)

IDE ->> Adapter: connect to IDE listener port

IDE ->>+ Adapter: request "attach"

Adapter ->>+ Debuggee_1: request "initialize", "attach"

Debuggee_1 -->>- Adapter: respond to "initialize", "attach"

Debuggee_1 ->>+ Debuggee_1: start debug session

Adapter ->>+ IDE: "ptvsd_subprocess" event

Adapter -->>- IDE: respond to "attach"

loop every message between IDE and Debuggee_1
Note over IDE,Debuggee_1: propagate message
end

IDE ->>- Adapter: connect to IDE listener port

IDE ->>+ Adapter: request "attach" to Debuggee_2

Adapter ->>+ Debuggee_2: request "initialize", "attach"

Debuggee_2 -->>- Adapter: respond to "initialize", "attach"

Debuggee_2 ->>+ Debuggee_2: start debug session

Adapter -->>- IDE: respond to "attach"

loop every message between IDE and Debuggee_2
Note over IDE,Debuggee_2: propagate message
end


Note right of Debuggee_2: user code exits

Debuggee_2 -X- Debuggee_2: exits

Adapter ->> IDE: "exited" event for Debuggee_2

Note right of Debuggee_1: user code exits

Debuggee_1 -X- Debuggee_1: exits

Adapter ->> IDE: "exited" event for Debuggee_1

Adapter -X Adapter: exits
```



## Important points

### How does the adapter know that connection from the server is for a subprocess?

By counting connections. The first one is for the root process, all others are for
subprocesses of that process.

### How does the adapter track server connections?

It creates a `Session` instance as soon as the server establishes a socket connection,
and maintains it until the corresponding debuggee process exits. Whenever the IDE
disconnects, the state of the instance is reset.

### How does the IDE know which subprocess to connect to?

It receives a "ptvsd_subprocess" event from the adapter (using the connection for the
root process), which contains host and port on which the adapter is listening for new
connections from the IDE, and PID of the subprocess. It then connects to the specified
host and port, and sends an "attach" request with "processId" from the event.

### How does the adapter know that connection from the IDE is for a specific subprocess?

The first connection is always for the root process. All subsequent connections are
for subprocesses, and must have "processId" specified in the "attach" request. The
adapter keeps track of PID for all processes that it tracks, and uses the PID specified
in the "attach" request to look up the corresponding `Session`.

### How does the server know that IDE has connected or disconnected?

The adapter sends an "initialized" request to the server for every one it receives from
the IDE, and sends a "disconnected" request every time the IDE disconnects (even if it
doesn't send one itself). The server uses those events to keep track of logical debug
sessions, even though the TCP connection is the same throughout the lifetime of the
debuggee. This allows it to enable/disable tracing, continue running if it was stopped
at a breakpoint etc.
