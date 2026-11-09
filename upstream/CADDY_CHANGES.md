# Upstream Caddy releases

Recorded from the official GitHub releases API.

## v2.11.7

Published: 2026-10-03T05:58:33Z

Source: https://github.com/caddyserver/caddy/releases/tag/v2.11.7

This patch release fixes regressions from 2.11.6, including a crash when proxying over HTTP/2 and streams that were cut off after a minute. **If you're on 2.11.6, we recommend upgrading.** It also adds support for the brand new `Incremental` header field (RFC 10036).

**Huge thank you to our sponsors for keeping the project alive with resources, and for our maintainers who triage and assist tirelessly in this relentless new age of AI.**

## Highlights

- **Fixed: crash and dropped streams caused by the new idle timeouts.** 2.11.6 introduced default idle read/write timeouts, which caused some problems:
  - In 2.11.6, the request body's idle deadline could outlive the handler that set it:
    - Over HTTP/2, Caddy could panic with a nil pointer dereference when the reverse proxy was still reading a request body after the handler had returned. (#8101)
    - Over HTTP/1.1, streaming responses to requests with a body, such as SSE clients that open the stream with a `POST`, were cut off exactly 60 seconds after the body was read. (#8103)

    Both are fixed in #8107. Thanks @steadytao!
  - Over HTTP/2, streaming responses that paused between writes for longer than [`write_idle`](https://caddyserver.com/docs/caddyfile/options#timeouts) (1 minute by default), like quiet SSE streams, were reset with a stream error. As documented, only a write that stalls should count. Thanks @WeidiDeng! (#8118, #8119)
- **Fixed: placeholders for missing cookies are empty again.** Since 2.11.6, places that keep unknown placeholders as written, like [`respond`](https://caddyserver.com/docs/caddyfile/directives/respond) headers, would output `{http.request.cookie.*}` literally when the cookie wasn't in the request. The same happened to `{http.request.tls.*}` on plain HTTP requests. Both are empty again. Thanks @steadytao! (#8019)
- **New: support for the [`Incremental`](https://www.rfc-editor.org/rfc/rfc10036.html) header field (RFC 10036).** It's the standard replacement for NGINX's proprietary `X-Accel-Buffering` header. If an upstream response has `Incremental: ?1`, [`reverse_proxy`](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy#streaming) forwards it immediately, the same as [`flush_interval -1`](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy#flush_interval), and [`encode`](https://caddyserver.com/docs/caddyfile/directives/encode) streams it instead of holding it back. Great for [Mercure](https://mercure.rocks), SSE and other streaming apps.
  - If the [`request_buffers`](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy#request_buffers) or [`response_buffers`](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy#response_buffers) options would prevent incremental forwarding, Caddy responds with `501 Not Implemented` instead of silently buffering, as the RFC requires.
  - The new [`proxy_status_name`](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy#proxy_status_name) option adds a `Proxy-Status` header to those responses, explaining why the message was refused.

  Thanks @dunglas! (#8020)
- **Faster TLS handshakes:** When nothing subscribes to certificate events and debug logging is off, CertMagic no longer builds event data for every handshake. Certificate lookup per handshake is about twice as fast, with 10 allocations instead of 15. Thanks @u5surf! (#8010)
- **Unix sockets:** When a reload moves a listener (or the admin endpoint) off a Unix socket, the old socket now closes right away and its file is removed. Before, clients connecting to the old path would hang until the next garbage collection, about 2 minutes later. Thanks @littfed! (#8061)
- **Headers handler:** Multiple `Set-Cookie` values in a JSON config's `set` are now sent as separate header fields, instead of being joined with commas into one field that clients can't parse. Thanks @Indra55! (#8080)
- **`caddy fmt`** no longer deletes an opening brace at the very end of the input. Thanks @n0liu! (#8047)

## What's Changed
* events: tell CertMagic which events are worth emitting by @u5surf in https://github.com/caddyserver/caddy/pull/8010
* feat: implement the Incremental header field (RFC 10036) by @dunglas in https://github.com/caddyserver/caddy/pull/8020
* caddyfile: Keep an opening brace that ends the input by @n0liu in https://github.com/caddyserver/caddy/pull/8047
* listeners: close unix socket immediately and unlink file on reload by @littfed in https://github.com/caddyserver/caddy/pull/8061
* reverseproxy: stabilise half-close test by @steadytao in https://github.com/caddyserver/caddy/pull/8049
* caddyhttp: keep absent optional placeholders empty by @steadytao in https://github.com/caddyserver/caddy/pull/8019
* headers: Preserve separate Set-Cookie values by @Indra55 in https://github.com/caddyserver/caddy/pull/8080
* caddyhttp: end request-body deadline ownership with handler by @steadytao in https://github.com/caddyserver/caddy/pull/8107
* timeouts: fix idle writer terminate h2 response writers between writes by @WeidiDeng in https://github.com/caddyserver/caddy/pull/8119

## New Contributors
* @n0liu made their first contribution in https://github.com/caddyserver/caddy/pull/8047
* @littfed made their first contribution in https://github.com/caddyserver/caddy/pull/8061

**Full Changelog**: https://github.com/caddyserver/caddy/compare/v2.11.6...v2.11.7

## v2.11.8

Published: 2026-11-04T01:16:09Z

Source: https://github.com/caddyserver/caddy/releases/tag/v2.11.8

This patch release is a big batch of bug fixes and security hardening, plus a handful of small additions. This release is cut from our `2.11` maintenance branch: fixes are backported from master. **We recommend upgrading, especially if you serve PHP or use `{host}` in file paths.**

**Huge thank you to our sponsors for keeping the project alive with resources, and for our maintainers who triage and assist tirelessly in this relentless new age of AI.**

:warning: **Please read the breaking changes below before upgrading.** Most of them reject configs or requests that never did what they looked like they did, so most setups won't notice.

## Highlights

- **Idle timeouts, round two.** More fixes for the idle read/write timeouts introduced in 2.11.6:
  - Per-route [`timeouts`](https://caddyserver.com/docs/caddyfile/directives/timeouts) now take precedence over the server-wide `read_body_idle` / `write_idle`, and nested `timeouts` use the innermost one. (#8121)
  - Over HTTP/2, a handler that paused reading the request body (like `reverse_proxy` uploading to a slow upstream) no longer loses the body and fails with 502. (#8125)
  - Deadlines set by handlers now act as a ceiling instead of being overridden, so things like Mercure's `dispatch_timeout` and FrankenPHP's `request_body_timeout` work again. Thanks @dunglas! (#8145, #8284)
  - HTTP/1.1 uploads that time out with a little body left no longer hang instead of sending the error response. Thanks @SiyXo511! (#8178)
- **Binding privileged ports with fewer capabilities (Linux):** If `CAP_NET_BIND_SERVICE` is permitted but not effective, Caddy raises it just for binding a privileged port. Packagers can use `setcap cap_net_bind_service=+p` instead of `+ep`, so Caddy still starts under `--cap-drop ALL`, OpenShift's `restricted-v2`, or systemd units with an empty `CapabilityBoundingSet=`. It also follows the kernel's `ip_unprivileged_port_start` instead of assuming 1024. (#8102, #8253)
- **Small additions:**
  - new `log_level` directive to set the access log level for matching requests, e.g. `log_level @healthchecks DEBUG` (#8201)
  - new `{time.now.rfc3339}` placeholder. Thanks @steadytao! (#8140)
  - new `not` matcher for TLS connection policies. Thanks @simonether! (#8138)
  - the `tls` matcher can be used in CEL [`expression`](https://caddyserver.com/docs/caddyfile/matchers#expression) matchers: `tls()`, `tls('complete')`, `tls('early_data')`. Thanks @stackedbyaradhya! (#8088)
- **Reverse proxy:**
  - headers you set yourself (like `Strict-Transport-Security` via [`header`](https://caddyserver.com/docs/caddyfile/directives/header)) are no longer lost when the upstream sends a 1xx response first, like 103 Early Hints (#8169)
  - request trailer values are forwarded, not just their names. Thanks @krishsinghhura! (#8246)
  - request-only `expression`s in `lb_retry_match` no longer retry successful responses (a regression since 2.11.3) (#8168)
  - dial errors through a forward proxy and to FastCGI backends are retried like other dial errors. Thanks @adarshxsh and @zemamba! (#8264, #8172)
  - `weighted_round_robin` no longer panics with fewer weights than upstreams, and no longer picks an unavailable upstream when there's only one weight; `random_choose` picks the least loaded host when all are busy (#8159, #8320, #8160)
  - with `request_buffers` / `response_buffers unlimited`, a body that fails partway is no longer treated as complete (#8207)
  - connections and sockets are no longer leaked when a protocol upgrade (e.g. WebSocket) fails during setup, or when a `handle_response` status isn't a number. Thanks @Version2beta and @BenMacha! (#8269, #8318)
  - HTTP/3 client cancellations are logged at debug level instead of as warnings. Thanks @larrasket! (#8135)
- **[`encode`](https://caddyserver.com/docs/caddyfile/directives/encode):** `If-None-Match` lists and weak tags get 304s properly (#8128), HEAD responses no longer get a bogus `Content-Length` (#8150), and `Accept-Encoding` / `Cache-Control` split across several header lines are all taken into account, with faster header handling in the proxy too. Thanks @Indra55, @jayhemnani9910 and @dunglas! (#8025)
- **PHP / FastCGI:** a `Location` response without a `Status` is now a 302 redirect, as CGI specifies (#8209), and an app that writes more than its declared `Content-Length` (like a PHP warning after the page) no longer corrupts HTTP/1.1 responses or kills HTTP/2 connections. Thanks @Sulaiman-Dauda! (#8212)
- **TLS & ECH:**
  - when Caddy rejects Encrypted ClientHello, it now sends retry configs, so clients with stale ECH configs can recover. Thanks @videah! (#8142)
  - an ECH public name that also has its own site block keeps that site's TLS settings (#8156)
  - `client_auth` modes `request` and `verify_if_given` no longer reject clients without a certificate when verifiers are configured (#8251)
  - a site block spanning several listener addresses no longer lets one listener's TLS connection policy (including client authentication) overwrite another's. Thanks @steadytao! (#8192)
  - repeated matcher lines in a TLS policy `match` block are all applied, not just the first. Thanks @simonether! (#8137)
  - merged automation policies keep a specific domain's policy ahead of a wildcard's (#8287), and an ACME issuer's `network_proxy` survives re-provisioning (#8288)
- **Caddyfile:**
  - `caddy run` prints the error again when startup fails, instead of silently exiting with code 1. Thanks @IndraGunawan! (#8180)
  - routes in a group that already matched no longer run their matchers, which fixes e.g. `try_files {path} {path}.html?{query} =404` returning 404 for everything (#8189)
  - multiple [`handle_errors`](https://caddyserver.com/docs/caddyfile/directives/handle_errors) blocks and [`vars`](https://caddyserver.com/docs/caddyfile/directives/vars) now follow Caddyfile order (#8195, #8197)
  - each `?Field` default in a [`header`](https://caddyserver.com/docs/caddyfile/directives/header) block is checked on its own, and respects `match` (#8217)
  - `import` shows the real OS error for files it can't read (#8163), negative `{args[...]}` indices no longer panic (#8316), and very long heredoc markers no longer make parsing crawl (#8203, #8249)
- **[`file_server`](https://caddyserver.com/docs/caddyfile/directives/file_server):** a path below a regular file (`/index.php/foo`) is a 404 again and works with `pass_thru` (#8131); `browse` handles symlinks in directories with escaped names (#8152) and offsets past the end (#8213)
- **[`templates`](https://caddyserver.com/docs/caddyfile/directives/templates):** template errors no longer keep stale `Content-Length` / `Etag` headers (#8149), bodyless responses no longer get `Content-Length: 0` (which broke iOS PWAs) (#8153), plus fixes for `humanize` time layouts with colons and front matter closed with `...` (#8215, #8259)
- **Logging:** `include` of a parent namespace includes its child modules (#8221), `dir_mode from_file` no longer creates unusable directories (#8225), and log routing to a site's logger ignores Host case (#8176)
- **Admin API:** with remote admin `access_control`, a request is allowed if any permission entry permits it, not just the first (#8317), and `Cache-Control: must-revalidate` is recognized alongside other directives (#8330)
- **Other fixes:** `caddy hash-password` handles Windows line endings and input without a final newline (#8227), a data race in the `basic_auth` cache is gone (#8278), the Windows service no longer gets stuck in `START_PENDING` (#8274), and [`uri`](https://caddyserver.com/docs/caddyfile/directives/uri) `strip_prefix` / `strip_suffix` handle percent-escapes and literal `%` correctly (#8005, #8345)
- **Release builds use Go 1.27** (Go 1.26 is still the minimum to build Caddy). (#8210)

## :warning: Breaking changes

- **Requests with an invalid or dots-only host (like `..`) are rejected with `400`** on every protocol, before any route runs. Before, HTTP/2 and HTTP/3 also accepted hosts containing `/` or `\`. (#8328)
- **[`request_body`](https://caddyserver.com/docs/caddyfile/directives/request_body) `max_size`** now rejects a request with `413` as soon as its `Content-Length` is over the limit, even if nothing would have read the body. (#8337)
- **`php_fastcgi` sites without an `index.php`:** requests for paths that don't exist are now sent to PHP as `index.php`, as the documented `first_exist_fallback` try policy always promised, instead of falling through to `file_server` and returning `404`. Also, `PATH_INFO` and `DOCUMENT_URI` are now derived from the normalized path (repeated slashes merged, `.` segments removed); `REQUEST_URI` is unchanged.
- **A `try_files` / `file` candidate ending in `/` only matches a directory**, so `/foo.txt/` no longer matches the file `/foo.txt`. (#8326)
- **[`encode`](https://caddyserver.com/docs/caddyfile/directives/encode)** now compresses responses even when the *request* has `Cache-Control: no-transform` (a response's `no-transform` is still honored), and responses that could have been encoded always get `Vary: Accept-Encoding`. To keep the old behavior: `@transformable not header Cache-Control *no-transform*` and `encode @transformable`. Malformed forms like `no-cache; no-transform` no longer disable compression. (#8301, #8025)
- **Stricter config validation.** Some configs that were silently accepted (and didn't do what you'd expect) are now errors:
  - more than one `expression` line in the same matcher set (combine them with `&&`) (#8183)
  - unknown TLS `curves` or `protocol_min` / `protocol_max` names, like `TLS1.3` instead of `tls1.3`, which used to be silently ignored (#8266)
  - a repeated `sni_regexp` in a TLS policy `match` block (#8137)
  - `ip_mask` log filter sizes out of range, like `33` for IPv4 (#8241)
  - `basic_auth` usernames that end up identical after placeholder expansion (#8315)
  - ports longer than 11 characters (#8277)
- **Evaluation order now follows the Caddyfile** for `handle_errors` blocks with status codes and for `vars` with non-path matchers. If you had overlapping codes or set the same variable twice, a different block or value may now win. (#8195, #8197)

## Security fixes

Thank you to everyone who reported responsibly and helped with patches:

- caddyhttp: A `Host` / `:authority` value with dot segments or slashes could escape the intended directory when used in file paths, like `root /srv/sites/{host}`, and with `php_fastcgi` even execute files outside it. Such hosts are now rejected (see above). Thanks @dunglas. (GHSA-r766-rf9f-588h, #8328)
- fastcgi: `SCRIPT_FILENAME` is now derived from the same normalized path that path matchers see, so a route protected by a path matcher can't be made to run a different script, e.g. with `/admin.php/../../other.php`. The `php_fastcgi` rewrite also always runs now (see above). Thanks @pamnario. (GHSA-f278-mgc7-46j3)
- fileserver: The `file` matcher no longer resolves paths like `/.env/./` to the regular file, which bypassed path rules such as `path *.env`. Thanks @dunglas. (GHSA-25cw-38mq-q7m6, #8326)
- rewrite: `{http.matchers.file.remainder}` is now escaped before rewriting, so double-encoded path info (like `..%252f`) can't turn into `../` after path rules have run. Thanks @dunglas. (GHSA-69hv-5jfc-mvmv, #8325)
- fileserver: When neither `HOME` nor `XDG_DATA_HOME` is set, Caddy's data directory falls back to `./caddy`, and a `file_server` serving the working directory could expose certificates and private keys. That directory is now always hidden. Thanks @dunglas. (GHSA-jf74-f69g-hcj9, #8327)
- fastcgi: The `php_fastcgi` trailing-slash redirect for directories with an `index.php` can no longer be turned into an open redirect to another site. Thanks @sam-kota. (#8285)
- fileserver: Files excluded with `hide` no longer show up in `browse` listings, and hidden `precompressed` sidecars are no longer served. Thanks @agammann. (#8155)
- reverseproxy: Hop-by-hop headers are stripped from 1xx responses and from `copy_response_headers` in `handle_response`, completing the fix for CVE-2026-55458. Thanks @SssiiiSssii1 and @tomholford. (GHSA-8qx7-j2v2-x6q5, #8256, #8270)
- logging: The `query` log filter now parses request URIs like the server does, so parameters after a `#` are redacted too. Thanks @jayhemnani9910. (#8255)

:warning: These security patches may be breaking if your application relies on the buggy behaviors.

:rotating_light: **Notice for Caddy plugin maintainers: Dependabot will probably alert you to the security fixes in Caddy and urge you to upgrade it in your `go.mod` file. Please ONLY upgrade the Caddy dependency if there's a change to an exported API your plugin uses.**

Thank you to everyone who was involved in this release, especially our 28 new contributors! :tada:

## What's Changed
* core: Raise CAP_NET_BIND_SERVICE when binding privileged ports by @francislavoie in https://github.com/caddyserver/caddy/pull/8102
* timeouts: take precedence over server-wide and enclosing idle timeouts by @francislavoie in https://github.com/caddyserver/caddy/pull/8121
* encode: Fix ETag list matching by @Indra55 in https://github.com/caddyserver/caddy/pull/8128
* fileserver: treat a path below a regular file as not found by @klokv in https://github.com/caddyserver/caddy/pull/8131
* reverseproxy: log HTTP/3 client cancellations at debug level by @larrasket in https://github.com/caddyserver/caddy/pull/8135
* caddytls: keep repeated matchers in nested matcher sets by @simonether in https://github.com/caddyserver/caddy/pull/8137
* core: add RFC 3339 time placeholder by @steadytao in https://github.com/caddyserver/caddy/pull/8140
* caddytls: add not matcher for TLS handshakes by @simonether in https://github.com/caddyserver/caddy/pull/8138
* caddyhttp: only bound HTTP/2 body reads in flight with the idle timeout by @francislavoie in https://github.com/caddyserver/caddy/pull/8125
* caddyhttp: document that negative idle timeouts disable them by @dunglas in https://github.com/caddyserver/caddy/pull/8146
* fileserver: stat symlink targets by decoded path in browse listings by @awss1i in https://github.com/caddyserver/caddy/pull/8152
* caddytls: Send ECH retry configs when rejecting ECH by @videah in https://github.com/caddyserver/caddy/pull/8142
* caddyfile: surface OS error when an import file is inaccessible by @Kshot3000 in https://github.com/caddyserver/caddy/pull/8163
* reverseproxy: Pick the least loaded host in random_choose when all are busy by @jayhemnani9910 in https://github.com/caddyserver/caddy/pull/8160
* reverseproxy: Don't panic in weighted_round_robin with fewer weights than upstreams by @jayhemnani9910 in https://github.com/caddyserver/caddy/pull/8159
* caddyhttp: let handler write deadlines cap the idle write timeout by @dunglas in https://github.com/caddyserver/caddy/pull/8145
* fileserver: apply hide rules to browse entries and precompressed sidecars by @agammann in https://github.com/caddyserver/caddy/pull/8155
* templates: Delete file headers on any template error by @jayhemnani9910 in https://github.com/caddyserver/caddy/pull/8149
* fastcgi: classify dial failures for retry by @zemamba in https://github.com/caddyserver/caddy/pull/8172
* go.mod: update golang.org/x/net to v0.60.0 by @elee1766 in https://github.com/caddyserver/caddy/pull/8179
* reverseproxy: Keep own headers after 1xx responses by @jayhemnani9910 in https://github.com/caddyserver/caddy/pull/8169
* httpcaddyfile: keep a site block's TLS policy for ECH public names by @awss1i in https://github.com/caddyserver/caddy/pull/8156
* encode: Don't write an empty encoded stream for HEAD responses by @jayhemnani9910 in https://github.com/caddyserver/caddy/pull/8150
* caddyhttp: ignore case when matching hosts in logger_names by @tbshfr in https://github.com/caddyserver/caddy/pull/8176
* reverseproxy: Only retry responses for expressions that use response data by @jayhemnani9910 in https://github.com/caddyserver/caddy/pull/8168
* cmd: unbuffer default logger on startup failure by @IndraGunawan in https://github.com/caddyserver/caddy/pull/8180
* caddyhttp: preserve expired request-body read deadlines by @SiyXo511 in https://github.com/caddyserver/caddy/pull/8178
* caddyhttp: skip matchers for satisfied route groups by @jayhemnani9910 in https://github.com/caddyserver/caddy/pull/8189
* caddyhttp: Reject repeated expression matchers in a matcher set by @jayhemnani9910 in https://github.com/caddyserver/caddy/pull/8183
* httpcaddyfile: isolate TLS policies across listeners by @steadytao in https://github.com/caddyserver/caddy/pull/8192
* httpcaddyfile: Keep handle_errors blocks in Caddyfile order by @jayhemnani9910 in https://github.com/caddyserver/caddy/pull/8195
* httpcaddyfile: keep source order for vars with non-comparable matchers by @Icyjerry in https://github.com/caddyserver/caddy/pull/8197
* caddyfile: avoid quadratic heredoc marker scanning by @francislavoie in https://github.com/caddyserver/caddy/pull/8203
* httpcaddyfile: Add log_level directive for access logs by @francislavoie in https://github.com/caddyserver/caddy/pull/8201
* templates: avoid zero content length for bodyless responses by @elee1766 in https://github.com/caddyserver/caddy/pull/8153
* reverseproxy: Don't drop read errors with unlimited buffers by @jayhemnani9910 in https://github.com/caddyserver/caddy/pull/8207
* fastcgi: Use 302 for a Location response without Status by @jayhemnani9910 in https://github.com/caddyserver/caddy/pull/8209
* fileserver: return an empty listing for offsets past the end by @shanejonas in https://github.com/caddyserver/caddy/pull/8213
* templates: preserve colons in humanize time layouts by @SiyXo511 in https://github.com/caddyserver/caddy/pull/8215
* logging: include module logs from its parent namespace by @omaresmael in https://github.com/caddyserver/caddy/pull/8221
* logging: Use the default file mode for dir_mode from_file by @jayhemnani9910 in https://github.com/caddyserver/caddy/pull/8225
* caddyauth: handle CRLF and unterminated hash-password input by @jayhemnani9910 in https://github.com/caddyserver/caddy/pull/8227
* headers: evaluate conditional defaults independently by @jayhemnani9910 in https://github.com/caddyserver/caddy/pull/8217
* ci: fix exhaustive linting by @steadytao in https://github.com/caddyserver/caddy/pull/8238
* caddyfile: check heredoc markers without a regexp by @awss1i in https://github.com/caddyserver/caddy/pull/8249
* logging: Reject out-of-range `ip_mask` CIDRs by @jayhemnani9910 in https://github.com/caddyserver/caddy/pull/8241
* caddytls: skip client cert verifiers when no certificate is presented by @awss1i in https://github.com/caddyserver/caddy/pull/8251
* logging: Parse request URIs in the `query` filter like the server does by @jayhemnani9910 in https://github.com/caddyserver/caddy/pull/8255
* reverseproxy: preserve request trailer values by @krishsinghhura in https://github.com/caddyserver/caddy/pull/8246
* core: Retry privileged binds on EACCES instead of checking port < 1024 by @francislavoie in https://github.com/caddyserver/caddy/pull/8253
* templates: use the earliest front matter closing fence by @jayhemnani9910 in https://github.com/caddyserver/caddy/pull/8259
* reverseproxy: strip hop-by-hop headers from interim responses by @SssiiiSssii1 in https://github.com/caddyserver/caddy/pull/8256
* reverseproxy: retry dial errors wrapped by a forward proxy by @adarshxsh in https://github.com/caddyserver/caddy/pull/8264
* caddyhttp: add CEL expression support to the tls matcher by @stackedbyaradhya in https://github.com/caddyserver/caddy/pull/8088
* windows: serialise service status updates by @krishsinghhura in https://github.com/caddyserver/caddy/pull/8274
* reverseproxy: close backend body and hijacked socket on upgrade setup failures by @Version2beta in https://github.com/caddyserver/caddy/pull/8269
* replacer: cache file lookups and cap them by @mohammed90 in https://github.com/caddyserver/caddy/pull/8248
* reverseproxy: strip hop-by-hop headers when copying response headers by @tomholford in https://github.com/caddyserver/caddy/pull/8270
* fastcgi: Stop response bodies at the declared Content-Length by @Sulaiman-Dauda in https://github.com/caddyserver/caddy/pull/8212
* caddytls: validate curve and protocol names, compare protocol IDs by @HakeemTheEmperor in https://github.com/caddyserver/caddy/pull/8266
* caddytls: keep ACME issuer network proxy after RebuildCertMagic by @k4lleanka in https://github.com/caddyserver/caddy/pull/8288
* fastcgi: keep the php_fastcgi directory redirect on the same origin by @sam-kota in https://github.com/caddyserver/caddy/pull/8285
* build(deps): bump github.com/go-chi/chi/v5 from 5.3.2 to 5.4.0 by @dependabot[bot] in https://github.com/caddyserver/caddy/pull/8298
* caddyhttp: document CEL raw strings for regexp patterns by @francislavoie in https://github.com/caddyserver/caddy/pull/8280
* caddyhttp: optimise header access and fix encoding negotiation by @dunglas in https://github.com/caddyserver/caddy/pull/8025
* caddyhttp: let handler read deadlines cap the idle read timeout by @dunglas in https://github.com/caddyserver/caddy/pull/8284
* httpcaddyfile: preserve automation policy precedence when merging by @bwisn in https://github.com/caddyserver/caddy/pull/8287
* ci: Use macos-latest runner instead of pinning macos-14 by @francislavoie in https://github.com/caddyserver/caddy/pull/8312
* encode: ignore request no-transform, vary identity responses on Accept-Encoding by @dunglas in https://github.com/caddyserver/caddy/pull/8301
* core: reject overlong ports in ParseNetworkAddress by @jasperdingg in https://github.com/caddyserver/caddy/pull/8277
* caddyauth: check basic_auth username uniqueness after placeholder expansion by @10kartik in https://github.com/caddyserver/caddy/pull/8315
* rewrite: escape file matcher remainder before rewriting by @dunglas in https://github.com/caddyserver/caddy/pull/8325
* fileserver: don't match regular file when path ends by slash by @dunglas in https://github.com/caddyserver/caddy/pull/8326
* fileserver: hide the data directory when it is relative by @dunglas in https://github.com/caddyserver/caddy/pull/8327
* admin: better Cache-Control handling by @dunglas in https://github.com/caddyserver/caddy/pull/8330
* encode: use httpguts to look for Accept-Encoding in Vary by @dunglas in https://github.com/caddyserver/caddy/pull/8329
* deps: update x509roots/fallback by @elee1766 in https://github.com/caddyserver/caddy/pull/8333
* ci: test and release with Go 1.27 by @krishsinghhura in https://github.com/caddyserver/caddy/pull/8210
* caddyhttp: reject invalid and dots-only hosts on every protocol by @dunglas in https://github.com/caddyserver/caddy/pull/8328
* caddyhttp: correct path matcher doc on bare trailing wildcards by @datrixlab in https://github.com/caddyserver/caddy/pull/8006
* rewrite: fix strip_path_suffix decoding a literal '%' as an escape by @datrixlab in https://github.com/caddyserver/caddy/pull/8005
* reverseproxy: close upstream body when handle_response status is invalid by @BenMacha in https://github.com/caddyserver/caddy/pull/8318
* fileserver: handle empty files in size try policies by @BenMacha in https://github.com/caddyserver/caddy/pull/8322
* reverseproxy: skip unavailable upstream with a single weighted_round_robin weight by @BenMacha in https://github.com/caddyserver/caddy/pull/8320
* admin: authorize remote requests matching any permission entry by @BenMacha in https://github.com/caddyserver/caddy/pull/8317
* rewrite: treat only valid percent encodings as escapes by @steadytao in https://github.com/caddyserver/caddy/pull/8345
* caddyfile: reject negative import argument indices by @BenMacha in https://github.com/caddyserver/caddy/pull/8316
* requestbody: enforce max_size early using Content-Length by @dunglas in https://github.com/caddyserver/caddy/pull/8337
* caddyauth: avoid writing into the shared hash buffer by @VenkateshPanda0 in https://github.com/caddyserver/caddy/pull/8278
* ci: release changelogs since the previous published release, and workflow hardening by @francislavoie in https://github.com/caddyserver/caddy/pull/8341

## New Contributors
* @klokv made their first contribution in https://github.com/caddyserver/caddy/pull/8131
* @simonether made their first contribution in https://github.com/caddyserver/caddy/pull/8137
* @awss1i made their first contribution in https://github.com/caddyserver/caddy/pull/8152
* @videah made their first contribution in https://github.com/caddyserver/caddy/pull/8142
* @Kshot3000 made their first contribution in https://github.com/caddyserver/caddy/pull/8163
* @jayhemnani9910 made their first contribution in https://github.com/caddyserver/caddy/pull/8160
* @agammann made their first contribution in https://github.com/caddyserver/caddy/pull/8155
* @zemamba made their first contribution in https://github.com/caddyserver/caddy/pull/8172
* @tbshfr made their first contribution in https://github.com/caddyserver/caddy/pull/8176
* @SiyXo511 made their first contribution in https://github.com/caddyserver/caddy/pull/8178
* @Icyjerry made their first contribution in https://github.com/caddyserver/caddy/pull/8197
* @shanejonas made their first contribution in https://github.com/caddyserver/caddy/pull/8213
* @omaresmael made their first contribution in https://github.com/caddyserver/caddy/pull/8221
* @krishsinghhura made their first contribution in https://github.com/caddyserver/caddy/pull/8246
* @SssiiiSssii1 made their first contribution in https://github.com/caddyserver/caddy/pull/8256
* @adarshxsh made their first contribution in https://github.com/caddyserver/caddy/pull/8264
* @stackedbyaradhya made their first contribution in https://github.com/caddyserver/caddy/pull/8088
* @Version2beta made their first contribution in https://github.com/caddyserver/caddy/pull/8269
* @Sulaiman-Dauda made their first contribution in https://github.com/caddyserver/caddy/pull/8212
* @HakeemTheEmperor made their first contribution in https://github.com/caddyserver/caddy/pull/8266
* @k4lleanka made their first contribution in https://github.com/caddyserver/caddy/pull/8288
* @sam-kota made their first contribution in https://github.com/caddyserver/caddy/pull/8285
* @bwisn made their first contribution in https://github.com/caddyserver/caddy/pull/8287
* @jasperdingg made their first contribution in https://github.com/caddyserver/caddy/pull/8277
* @10kartik made their first contribution in https://github.com/caddyserver/caddy/pull/8315
* @datrixlab made their first contribution in https://github.com/caddyserver/caddy/pull/8006
* @BenMacha made their first contribution in https://github.com/caddyserver/caddy/pull/8318
* @VenkateshPanda0 made their first contribution in https://github.com/caddyserver/caddy/pull/8278

**Full Changelog**: https://github.com/caddyserver/caddy/compare/v2.11.7...v2.11.8

## v2.11.9

Published: 2026-11-05T01:30:24Z

Source: https://github.com/caddyserver/caddy/releases/tag/v2.11.9

This is a quick follow-up on top of 2.11.8, to fix a regression it introduced and a few more security issues, mostly in FastCGI. It contains only fixes backported from master, plus a couple of small additions. **If you're on 2.11.8 and serve PHP, we recommend upgrading.**

**Huge thank you to our sponsors for keeping the project alive with resources, and for our maintainers who triage and assist tirelessly in this relentless new age of AI.**

## Highlights

- **Fixed: PHP directory indexes (regression in 2.11.8).** A request for a directory with a trailing slash, like `/wp-admin/`, was matched by the directory itself instead of its `index.php`, so it never reached PHP and usually got a 404. This broke WordPress admin pages and other apps that serve an index through a trailing-slash URL. A `try_files` pattern now only matches a directory when it ends in `/`. Thanks @dunglas! (#8352)
- **Path matchers with placeholders** now work as expected: placeholders like `{env.FOO}` are no longer lower-cased into `{env.foo}` before they're looked up, and their values are compared case-insensitively against the request path, like static patterns. Thanks @BenMacha! (#8343)
- **New `plain_time_format` option for [`file_server browse`](https://caddyserver.com/docs/caddyfile/directives/file_server):** sets the time layout of plain-text directory listings (`Accept: text/plain`). Thanks @steffenbusch! (#8084)
- **Fewer allocations** in path cleaning, header rewriting and `weighted_round_robin` selection. Thanks @jvoisin! (#7842)
- **For plugin authors:** new `httpcaddyfile.Helper.IsNamedRoute()` tells a directive whether it's being parsed inside a [named route](https://caddyserver.com/docs/caddyfile/concepts#named-routes). (#8354)

## :warning: Breaking changes

- **Conflicting `client_auth` is now a Caddyfile error.** When two site blocks share TLS connection policies for the same hostname but set different `client_auth`, the adapter used to keep the first one and silently drop the other, which could quietly remove a stricter mTLS requirement. (#8306)
- **FastCGI requests that are ambiguous about which script they run get `400`:**
  - when the escaped path (which `%`-containing path matchers see) and the decoded path would select different scripts, e.g. `/public/tool.php%2f..%2f..%2fadmin%2ftool.php` (#8357)
  - on Windows, script paths with an 8.3 short name component (like `ADMINI~1`) or a `:` (NTFS alternate data streams) (#8356)
- **FastCGI `env` values now take precedence over request headers**, so a client can no longer override `HTTP_*` variables you set with `env` (see below). (#8358)

## Security fixes

Thank you to everyone who reported responsibly and helped with patches:

- fastcgi: A client could override any `HTTP_*` variable set with the FastCGI transport's (or `php_fastcgi`'s) `env` subdirective by sending a matching request header, for example choosing the user an application sees in `HTTP_X_AUTH_USER`. Configured values now win. Reported by @JebeenLee and @Camel4, fixed by @dunglas. (GHSA-q34h-28rj-5hjm, #8358)
- fastcgi: On Windows, NTFS 8.3 short names and alternate data streams could run a script that a path rule was meant to deny, completing the FastCGI fix from 2.11.8. Thanks @dunglas. (GHSA-9cr8-wmhh-39pm, #8356)
- fastcgi: Encoded slashes and dot segments could make a `%`-containing path matcher approve one script while another one runs. Thanks @dunglas. (#8357)
- fastcgi: Over HTTP/2, a `host` field sent next to `:authority` could make the application see a different host (`HTTP_HOST`) than the one Caddy routed the request to. Thanks @dunglas. (#8355)
- httpcaddyfile: A stricter `client_auth` could be silently dropped when merging TLS connection policies (see above). Thanks @sam-kota. (#8306)
- Updated `go-jose` to v4.1.6 for GHSA-mgcc-cww5-fp2q. (#8299)

:warning: These security patches may be breaking if your application relies on the buggy behaviors.

:rotating_light: **Notice for Caddy plugin maintainers: Dependabot will probably alert you to the security fixes in Caddy and urge you to upgrade it in your `go.mod` file. Please ONLY upgrade the Caddy dependency if there's a change to an exported API your plugin uses.**

## What's Changed
* caddyhttp: lower-case path patterns with placeholders at request time by @BenMacha in https://github.com/caddyserver/caddy/pull/8343
* httpcaddyfile: reject conflicting client_auth when merging TLS policies by @sam-kota in https://github.com/caddyserver/caddy/pull/8306
* build(deps): bump the actions-deps group across 1 directory with 10 updates by @dependabot[bot] in https://github.com/caddyserver/caddy/pull/8340
* build(deps): bump github.com/go-jose/go-jose/v4 from 4.1.5 to 4.1.6 by @dependabot[bot] in https://github.com/caddyserver/caddy/pull/8299
* fileserver: make plain-text browse time format configurable by @steffenbusch in https://github.com/caddyserver/caddy/pull/8084
* fileserver: only match a dir when the pattern ends by / by @dunglas in https://github.com/caddyserver/caddy/pull/8352
* httpcaddyfile: add Helper.IsNamedRoute by @dunglas in https://github.com/caddyserver/caddy/pull/8354
* fastcgi: take HTTP_HOST from the routed host only by @dunglas in https://github.com/caddyserver/caddy/pull/8355
* fastcgi: reject Win 8.3 aliases and alt data streams paths by @dunglas in https://github.com/caddyserver/caddy/pull/8356
* caddyhttp: presize buffers in hot paths to reduce allocations by @jvoisin in https://github.com/caddyserver/caddy/pull/7842
* fastcgi: let configured env variables override request headers by @dunglas in https://github.com/caddyserver/caddy/pull/8358
* fastcgi: reject paths whose escaped form selects another script by @dunglas in https://github.com/caddyserver/caddy/pull/8357

**Full Changelog**: https://github.com/caddyserver/caddy/compare/v2.11.8...v2.11.9
