# @lam/vulture/ws-plugin

`@lam/vulture/ws-plugin` adds WebSocket upgrades, message I/O, origin policy,
subprotocol negotiation, and per-message compression to
[`@lam/vulture`](https://github.com/thallium-solutions/lam-vulture). It is the
standalone Lam 1.17 package extracted from `lamserver_ws` in the
[Lammergeier language repository](https://github.com/thallium-solutions/lammergeier-lang).
The wire implementation uses
[`github.com/gorilla/websocket`](https://github.com/gorilla/websocket) v1.5.3,
matching the central library pin.

## Features

- `wsRoute` for a simple WebSocket GET endpoint.
- `wsRouteOpts` for exact origin allow-lists, server-selected subprotocols, and
  RFC 7692 permessage-deflate negotiation.
- Text and binary send/receive operations, ping, idempotent close, connection
  state, and an advanced native-connection escape hatch.
- The upgraded request remains an `@lam/vulture` `Request`, including query
  parameters, headers, cookies, context, and hooks executed before the route.
- Automatic connection close when a handler returns.

The package deliberately keeps `github.com/gorilla/websocket` as a separate Go
dependency, so applications that only use `@lam/vulture` HTTP routes do not ship
a WebSocket implementation.

## Requirements

- `lamc` 1.17.0 or newer within the compatible 1.x line (`^1.17`).
- `@lam/vulture` v1.0.0. The Git release is pinned in `lamlib.toml` and is
  resolved transitively for consumers.
- A Go toolchain supported by Lammergeier and Gorilla WebSocket v1.5.3.

## Installation

### Git release

Install the tagged source directly from this package's GitHub repository:

```bash
lamc install https://github.com/thallium-solutions/lam-vulture-ws-plugin.git@v1.0.0
```

Pin a release tag or commit for reproducible builds rather than tracking a
branch. The package manifest installs `@lam/vulture` v1.0.0 transitively.

### Registry

After the package is published to a configured Lam registry:

```bash
lamc install @lam/vulture/ws-plugin@1.0.0
```

A project may instead declare a compatible registry constraint and run
`lamc install`:

```toml
[dependencies]
"@lam/vulture/ws-plugin" = "^1.0.0"
```

### Local package

Install a checkout directly:

```bash
lamc install /path/to/lam-vulture-ws-plugin
```

For sibling-checkout development, keep canonical imports and use project-local
path resolution:

```toml
[dependencies]
"@lam/vulture/ws-plugin" = { path = "../lam-vulture-ws-plugin" }

[replace]
"@lam/vulture" = { path = "../lam-vulture" }
```

Then run `lamc install` in the application directory. The test runner uses the
same consumer shape without changing global state: it stages this checkout at
`extlibs/@lam/vulture/ws-plugin` and the sibling core checkout at
`extlibs/@lam/vulture`.

## Quick start

Import HTTP types from the core package and WebSocket APIs from this plugin:

```lammergeier
from @lam/vulture import Server, Request
from @lam/vulture/ws-plugin import WebSocket, wsRoute

func echo(ws: WebSocket, req: Request) {
    while not ws.isClosed() {
        message: str = ws.recv()
        if message == "" {
            return
        }
        if not ws.send(f"echo: {message}") {
            return
        }
    }
}

func main() {
    server: Server = Server()
    wsRoute(server, "/echo", echo)
    server.listen(8080)
}
```

Connect to `ws://127.0.0.1:8080/echo`. The handler runs once for the lifetime of
the upgraded connection. When it returns, the plugin sends a normal Close frame
and closes the underlying connection.

## Origin policy

`wsRoute` preserves the central helper's permissive default and accepts every
`Origin`. That is convenient for local development but is not a production
cross-origin policy. Use `wsRouteOpts` with an exact allow-list on internet-facing
servers:

```lammergeier
from @lam/vulture import Server, Request
from @lam/vulture/ws-plugin import WebSocket, wsRouteOpts

func events(ws: WebSocket, req: Request) {
    ws.send("connected")
}

func main() {
    server: Server = Server()
    wsRouteOpts(server, "/events", events, {
        "originAllowList": [
            "https://app.example.com",
            "https://admin.example.com",
        ],
    })
    server.listen(8080)
}
```

Matching is exact against the request's `Origin` header. With a non-empty list,
a missing or unlisted origin is rejected by the Gorilla upgrader with HTTP 403.
Use the complete origin (`scheme://host[:port]`), not a path or wildcard.
Authentication and authorization should still run in `@lam/vulture` hooks; an
origin check is not an identity check.

## Subprotocol negotiation

List protocols in server preference order. Gorilla selects the first supported
entry also offered by the client, and the handler reads the negotiated value
from `ws.subprotocol`:

```lammergeier
from @lam/vulture import Server, Request
from @lam/vulture/ws-plugin import WebSocket, wsRouteOpts

func rpc(ws: WebSocket, req: Request) {
    if ws.subprotocol == "jsonrpc-v2" {
        ws.send("{\"jsonrpc\":\"2.0\",\"result\":\"ready\",\"id\":1}")
        return
    }
    ws.send("ready")
}

func configure(server: Server) {
    wsRouteOpts(server, "/rpc", rpc, {
        "subprotocols": ["jsonrpc-v2", "chat-v1"],
        "originAllowList": ["https://app.example.com"],
    })
}
```

`ws.subprotocol` is `""` when no protocol is negotiated. Applications that
require a protocol should validate it in the handler and close unsupported
connections.

## Compression

Enable RFC 7692 permessage-deflate negotiation per route:

```lammergeier
wsRouteOpts(server, "/stream", streamHandler, {
    "compression": true,
    "originAllowList": ["https://app.example.com"],
})
```

Compression is used only when the client also requests it. It can reduce large
text payloads but costs CPU and can amplify secret-exposure risks when attacker-
controlled and secret data share compressed messages. Leave it disabled for
small messages or sensitive mixed-content streams.

Origin, subprotocol, and compression options can be combined:

```lammergeier
wsRouteOpts(server, "/socket", socketHandler, {
    "originAllowList": ["https://app.example.com"],
    "subprotocols": ["events-v1"],
    "compression": true,
})
```

## API

### Routes

```lammergeier
wsRoute(server, path, handler)
wsRouteOpts(server, path, handler, options)
```

A handler has the shape `func(ws: WebSocket, req: Request)`. Both helpers
register a GET route and bind the user handler during the normal
`@lam/vulture` request-hook pipeline. A successful HTTP upgrade hijacks the
response, so ordinary response serialization and successful-response hooks do
not write to that connection afterward.

`wsRouteOpts` recognizes:

| Key | Type | Behavior |
| --- | --- | --- |
| `originAllowList` | `list[str]` | Exact allowed `Origin` values; empty or omitted accepts all origins. |
| `subprotocols` | `list[str]` | Server-supported protocols in preference order. |
| `compression` | `bool` | Enables permessage-deflate negotiation when `true`. |

### `WebSocket`

| Member | Result | Notes |
| --- | --- | --- |
| `send(message)` | `bool` | Sends one UTF-8 text frame. |
| `recv()` | `str` | Blocks for the next text frame; skips binary frames and returns `""` on close/error. |
| `sendBytes(data)` | `bool` | Sends a native Go `[]byte` as one binary frame. |
| `recvBytes()` | `any` | Blocks for the next binary frame; skips text frames and returns `None` on close/error. |
| `ping()` | `bool` | Sends a Ping control frame. |
| `close()` | `None` | Best-effort normal close; safe to call repeatedly. |
| `isClosed()` | `bool` | Reports wrapper close/error state. |
| `subprotocol` | `str` | Protocol selected during the handshake, or `""`. |
| `rawConn()` | `any` | Returns `*websocket.Conn` for advanced native operations. |

Binary sending intentionally preserves the central API's native byte boundary.
For example, advanced code can obtain a Go byte slice with a narrowly scoped
`go!` expression before calling `sendBytes`. Prefer text messages when a native
byte value is not otherwise needed.

## Concurrency, deadlines, and lifecycle

- `recv` and `recvBytes` block. Run a receive loop through Lam concurrency APIs
  when the rest of the application must continue independently.
- Gorilla supports one concurrent reader and one concurrent writer. Serialize
  multiple writers in application code.
- `ping` is application-managed; the wrapper does not start a heartbeat loop.
- The wrapper marks itself closed on frame I/O errors. `recv() == ""` can also
  represent an empty text message, so call `isClosed()` when the distinction
  matters.
- `rawConn()` is the escape hatch for native read/write deadlines, control
  handlers, compression tuning, and frame features not represented by the
  stable Lam API. Those operations require Gorilla's native types and should
  remain in small `go!` boundaries.

## Implementation boundary

Connection state guards, close-state queries, and the missing-handler response
use Lam directly. Native Go remains where behavior depends on Gorilla frame
constants and connection methods, dynamic Go type assertions, HTTP
`ResponseWriter`/`Request` integration and hijacking, and the exact
`func(*Request, *Response)` callback type required by `@lam/vulture` hooks. The
hermetic test client likewise keeps WebSocket frames and its read deadline at
the native boundary. The copied uppercase test helper was replaced with the
behavior-equivalent `lamstrings.Strings.toUpper` call.

## Testing

Place complete sibling checkouts at `../lam-vulture` and
`../lam-vulture-ws-plugin`, then run:

```bash
python3 tests/run_tests.py
# or
lamc lib run test
```

The runner requires a compatible `lamc`, stages both packages in a temporary
consumer-style `extlibs` tree, compiles every `tests/test_*.lam` file without
cache, executes it, and compares stdout exactly with its `# expect:` directives.
It performs no registry or network installation.

## License

Apache-2.0. See `lamlib.toml` for package metadata.
