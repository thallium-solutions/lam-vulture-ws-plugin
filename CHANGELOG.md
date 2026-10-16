# @lam/vulture/ws-plugin Changelog

All notable changes to `@lam/vulture/ws-plugin` are documented here.

## 2.0.1 - 2026-10-16

### Fixed

- The `@lam/vulture` dependency pointed at the tag `v2.0.0`, which is not
  published (release tags are plain versions), so installing the package from
  Git failed. It now pins `@lam/vulture` `2.0.1`, the release this package is
  tested with.

## 2.0.0 - 2026-09-30

### Added

- Unsuffixed `wsUpgrade(req, res, options)` returning
  `Result[WebSocket]` for low-level typed upgrade handling.
- Stable WebSocket error kinds for closed connections, unavailable native
  connections, frame send/receive failures, invalid binary values,
  configuration failures, and upgrade failures.
- Explicit tests for empty text frames, binary frames, ping, closed-operation
  errors, invalid configuration, and non-HTTP upgrade attempts.

### Changed

- Changed `WebSocket.send`, `sendBytes`, and `ping` from boolean sentinels to
  `Result[bool]`.
- Changed `WebSocket.receive` to `Result[str]` and `receiveBytes` to `Result[any]`, so
  empty frames, normal closure, and transport failures are distinguishable.
- Replaced `wsRoute`/`wsRouteOpts` naming with `wsRoute` overloads. The
  four-argument overload accepts core `RouteOptions`; WebSocket configuration
  is validated from its metadata and route registration returns `Result[bool]`.
- Registered the upgrade handler through Vulture's typed `get` overload and a
  route-local pre-handler binding rather than mutating the server's global
  `onRequestHooks` list.
- Switched plugin response failures to fluent `code(...).text(...)` calls.
- Renamed the `WebSocket` constructor from `__init__` to `init`.
- Raised compatibility to Lam 1.18, `@lam/vulture` 2.0.0, and package version
  2.0.0.

### Testing

- Added installed-package WebSocket composition coverage for typed route hooks,
  policy validation, empty text/binary frames, ping, and closure failures.

### Removed

- Removed `wsRouteOpts`; use `wsRoute(server, path, handler, RouteOptions)`.
- Removed false, empty-string, and `None` failure sentinels from frame APIs.

## 1.0.0 - 2026-09-18

### Added

- Initial standalone WebSocket plugin release for `@lam/vulture` 1.0.0.
