# @lam/vulture/ws-plugin

`@lam/vulture/ws-plugin` adds WebSocket upgrades, text and binary frame I/O,
origin policy, subprotocol negotiation, and per-message compression to
[`@lam/vulture`](https://github.com/thallium-solutions/lam-vulture). The wire
implementation uses
[`github.com/gorilla/websocket`](https://github.com/gorilla/websocket) v1.5.3.

Version 2 follows `@lam/vulture` 2.0 conventions: expected failures use
unsuffixed `Result[T]` APIs, route configuration uses typed `RouteOptions`
overloads, and package classes use `init` constructors.

## Requirements

- `lamc` 1.18.0 or newer within the compatible 1.x line (`^1.18`).
- `@lam/vulture` v2.0.0. The Git release is pinned in `lamlib.toml`.
- A Go toolchain supported by Lammergeier and Gorilla WebSocket v1.5.3.

## Installation

Install the tagged Git release:

```bash
lamc install https://github.com/thallium-solutions/lam-vulture-ws-plugin.git@v2.0.0
```

After publication to a configured registry:

```bash
lamc install @lam/vulture/ws-plugin@2.0.0
```

Or declare a compatible dependency:

```toml
[dependencies]
"@lam/vulture/ws-plugin" = "^2.0.0"
```

For sibling-checkout development, retain canonical imports and use local path
resolution:

```toml
[dependencies]
"@lam/vulture/ws-plugin" = { path = "../lam-vulture-ws-plugin" }

[replace]
"@lam/vulture" = { path = "../lam-vulture" }
```

## Quick start

```lammergeier
from @lam/vulture import Request, Server
from @lam/vulture/ws-plugin import WebSocket, wsRoute

func echo(ws: WebSocket, _req: Request) {
    while not ws.isClosed() {
        incoming = ws.receive()
        if not incoming.ok() {
            return
        }
        message: str = incoming.unwrap()
        if not ws.send("echo: " + message).ok() {
            return
        }
    }
}

func main() {
    app: Server = Server()
    registered: bool = wsRoute(app, "/echo", echo).unwrap()
    listening: bool = app.listen(8080).unwrap()
}
```

Connect to `ws://127.0.0.1:8080/echo`. A handler runs for the lifetime of its
upgraded connection. The plugin sends a normal close frame and closes the
native connection when the handler returns or panics.

## Typed route options

`wsRoute` is overloaded rather than paired with an `Opts`-suffixed helper:

```lammergeier
wsRoute(server, path, handler) -> Result[bool]
wsRoute(server, path, handler, options: RouteOptions) -> Result[bool]
```

The second overload preserves all core `RouteOptions` behavior, including
per-route limits, timeouts, hooks, schemas, OpenAPI fields, and metadata.
WebSocket upgrade settings use these metadata keys:

| Key | Type | Behavior |
| --- | --- | --- |
| `originAllowList` | `list[str]` | Exact allowed `Origin` values; empty or omitted accepts all origins. |
| `subprotocols` | `list[str]` | Server-supported protocols in preference order. |
| `compression` | `bool` | Enables RFC 7692 permessage-deflate negotiation. |

Metadata is intentionally heterogeneous in core Vulture. The plugin validates
its keys before registering a route and returns
`WebSocketConfigurationError` for an invalid value instead of silently
ignoring it or panicking.

```lammergeier
from @lam/vulture import Request, Response, RouteOptions, Server
from @lam/vulture/ws-plugin import WebSocket, wsRoute

func authenticated(req: Request, res: Response) {
    if req.header("Authorization") == "" {
        res.code(401).text("missing credentials")
    }
}

func events(ws: WebSocket, _req: Request) {
    _sent: bool = ws.send("connected").unwrap()
}

func configure(app: Server) {
    options: RouteOptions = RouteOptions(0, 30000)
    _ = options.preHandler(authenticated)
    _ = options.metadata("originAllowList", [
        "https://app.example.com",
        "https://admin.example.com",
    ])
    _ = options.metadata("subprotocols", ["events-v2", "events-v1"])
    _ = options.metadata("compression", true)
    _registered: bool = wsRoute(app, "/events", events, options).unwrap()
}
```

Origin matching is exact against the request's `Origin` header. With a
non-empty allow-list, a missing or unlisted origin is rejected with HTTP 403.
Use complete origins (`scheme://host[:port]`), not paths or wildcards.
Authentication and authorization still belong in Vulture hooks; an origin
check is not an identity check.

`ws.subprotocol` contains the negotiated protocol or `""` when none was
selected. Compression is active only when the client also requests it. It can
reduce large messages but costs CPU and can expose secrets when attacker-
controlled and secret data share compressed messages.

## Result-based frame API

Operational failures never share a false, empty-string, or `None` sentinel
with valid data:

| Member | Result | Notes |
| --- | --- | --- |
| `send(message)` | `Result[bool]` | Sends one UTF-8 text frame. |
| `receive()` | `Result[str]` | Blocks for a text frame and skips binary frames. `Ok("")` is a valid empty frame. |
| `sendBytes(data)` | `Result[bool]` | Sends a native Go `[]byte` as one binary frame. |
| `receiveBytes()` | `Result[any]` | Blocks for a binary frame and skips text frames. An empty byte slice is successful. |
| `ping()` | `Result[bool]` | Sends a Ping control frame. |
| `close()` | `None` | Best-effort normal close; safe to call repeatedly. |
| `isClosed()` | `bool` | Reports wrapper close/error state. |
| `subprotocol` | `str` | Negotiated protocol or `""`. |
| `rawConn()` | `any` | Returns `*websocket.Conn` for advanced native operations. |

Error kinds are stable enough for callers to inspect through `result.error`:

- `WebSocketClosedError` — an operation was attempted after close, or a normal
  peer close was received.
- `WebSocketConnectionError` — the wrapper has no usable native connection.
- `WebSocketSendError` / `WebSocketReceiveError` — frame transport failed.
- `WebSocketDataError` — `sendBytes` did not receive a native `[]byte`.
- `WebSocketConfigurationError` — route/upgrade metadata is invalid.
- `WebSocketUpgradeError` — no live HTTP transport was available or the
  handshake failed.

A receive loop can therefore distinguish a valid empty message from closure
without consulting `isClosed`:

```lammergeier
result = ws.receive()
if not result.ok() {
    print(str(result.error))
    return
}
message: str = result.unwrap()  # may legitimately be ""
```

Binary methods retain the package's native byte boundary. Keep construction or
inspection of Go `[]byte` values in a narrowly scoped `go!` block, or prefer
text frames when a native byte value is not otherwise required.

## Low-level upgrade

`wsRoute` is the normal API. Plugins that already own a Vulture route can use
the unsuffixed low-level operation:

```lammergeier
wsUpgrade(req, res, options: RouteOptions) -> Result[WebSocket]
```

Configuration, missing native HTTP transport, and Gorilla handshake failures
are returned as typed errors. Missing-transport and invalid-configuration HTTP
responses use Vulture's fluent `res.code(...).text(...)` API. Gorilla writes
its own protocol handshake failure response; the plugin marks that response as
handled so Vulture does not write a second one.

Callers of `wsUpgrade` own the successful connection and should close it. The
higher-level `wsRoute` overloads close automatically.

## Concurrency and lifecycle

- `receive` and `receiveBytes` block. Use Lam concurrency when other work must
  continue independently.
- Gorilla supports one concurrent reader and one concurrent writer. Serialize
  multiple writers in application code.
- `ping` is application-managed; the wrapper does not start a heartbeat loop.
- Any frame I/O failure marks the wrapper closed.
- `rawConn()` is the escape hatch for native deadlines, control handlers,
  compression tuning, and frame features outside the stable Lam API.

## Migrating from 1.x

Version 2 is intentionally breaking:

- Replace `wsRouteOpts(server, path, handler, dict)` with the four-argument
  `wsRoute` overload and a `RouteOptions` value. Move WebSocket settings into
  `RouteOptions.metadata`.
- Handle or unwrap the `Result[bool]` returned by `wsRoute`.
- Handle `Result` from `send`, `sendBytes`, `ping`, `receive`, and `receiveBytes`.
  `receive() == ""` and `receiveBytes() == None` are no longer close/error tests.
- Custom construction follows Lam 1.18's `init` convention; `__init__` is gone.
- Upgrade and configuration failures are explicit `Result` errors.

See [CHANGELOG.md](CHANGELOG.md) for the release summary.

## Implementation boundary

Route registration, hook registration through `RouteOptions.preHandler`,
response errors, Result handling, and connection dispatch use Lam APIs. The
route-local binding callback is constructed at the native boundary because Lam
1.18 cannot lower a capturing void lambda to Vulture's exact
`func(*Request, *Response)` hook type. Native Go also remains where Gorilla
frame constants and connections, `http.ResponseWriter`, and dynamic metadata
validation require it.

## Testing

Place sibling checkouts at `../lam-vulture` and
`../lam-vulture-ws-plugin`, then run:

```bash
python3 tests/run_tests.py
# or
lamc lib run test
```

The runner requires `lamc ^1.18`, stages both packages in a temporary
consumer-style `extlibs` tree, compiles every `tests/test_*.lam` file without
cache, executes it, and compares stdout with its `# expect:` directives. It
performs no registry or network installation.

## License

Apache-2.0. See `LICENSE` and `lamlib.toml`.
