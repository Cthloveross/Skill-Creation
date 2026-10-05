---
name: harden-erlang-ssh-authentication-boundary
description: Investigate and make a small state-oriented fix in an Erlang/OTP SSH server when pre-authentication SSH messages can reach channel, service, or application execution. Use this for source-tree vulnerability repairs that must preserve normal authenticated SSH behavior.
---

# Harden the SSH authentication boundary

## Security invariant

An SSH packet being syntactically decoded does not authorize its effects. Any inbound
message that can create a channel, invoke a channel/global/service operation, or reach
application command handling must be stopped unless the connection state has completed
user authentication. Authentication protocol traffic itself must remain available in its
proper pre-authentication states.

The desired repair is a narrow change at the common state-machine dispatch boundary, not
a filter tied to one command payload, packet ordering, or application callback.

## Inputs and prerequisites

* An editable Erlang/OTP source tree.
* The relevant SSH server code is present (normally under `lib/ssh`).
* The executor can inspect source and use its normal editing tools. Compilation or tests
  are optional when the task explicitly says not to build, but source-level validation is
  still required.

Do not assume a particular OTP release, state-function name, record layout, or disconnect
helper. Reuse the conventions already present in the target source.

## Investigation workflow

1. Locate the SSH connection handler/state-machine module and its inbound decoded-message
   dispatch. Search for SSH message record names, state callbacks (`handle_event`,
   `handle_msg`, `StateName(...)`, etc.), and the code which invokes channel or subsystem
   handling.
2. Run the packaged scanner to make an inventory of likely dispatch sites. It is an aid,
   not a proof of authorization:

   ```sh
   python3 scripts/scan_erlang_dispatch.py <<'JSON'
   {"root":"/path/to/otp-source"}
   JSON
   ```

   The script writes one JSON object containing candidate files, line numbers, and source
   context. Its input schema is:

   * `root` (required string): source-tree root;
   * `message_patterns` (optional array of strings): record/tag text to search for;
   * `max_hits` (optional positive integer): maximum reported occurrences per pattern.

3. Trace every candidate from packet decoding to the state callback. Identify:
   * the states before authentication is accepted;
   * the state or explicit data flag that establishes successful authentication;
   * the exact transition that enters that authenticated state;
   * all paths by which channel opening, channel requests (including command execution),
     global/application requests, or comparable capability-bearing actions reach their
     handlers.

   Do not treat a state whose name merely sounds connected as authenticated without
   verifying its transition conditions. Conversely, do not block required transport key
   exchange, user-authentication service negotiation, or user-authentication messages.

4. Find the narrowest common authorization point shared by the capability-bearing paths.
   Prefer a state-machine clause/guard that rejects these decoded messages whenever the
   current state is not authenticated. If the module has a single generic inbound-message
   clause before the channel/application dispatch, place the invalid-state handling before
   that generic clause. If it has explicit per-state clauses, add a compact invalid-state
   clause set in the pre-auth states using the module's established error/disconnect
   convention.

5. Make the smallest compatible patch. The rejection must be terminal for that packet:
   it must return the existing protocol-error/disconnect outcome (or an established
   non-dispatch rejection outcome) rather than fall through to execution. Match Erlang
   patterns precisely and preserve the callback return tuple and state transition format.
   Do not add a payload blacklist, command-name special case, or an independent notion of
   authentication that can drift from the state machine.

6. Preserve the authenticated clauses and their ordering. A valid channel open/request
   after successful authentication must continue to reach the original code. Keep ordinary
   behavior for unrelated invalid SSH messages unchanged unless the common boundary
   intentionally handles them too.

## Erlang-specific review checklist

Review the edited functions for all of the following before delivering the source change:

* A broad message pattern does not appear before the new invalid-state pattern and swallow
  it. Erlang selects clauses top-to-bottom.
* Guard expressions, record names, tuple arity, semicolons, and final periods are valid.
* The new rejection uses a return shape accepted by the surrounding state callback.
* No pre-auth state can fall through to a channel/application invocation after the new
  clause. Check each state transition and any generic fallback explicitly.
* Authentication success still reaches the authenticated state, and the authenticated
  message clauses remain reachable.
* Existing error/disconnect helpers are used consistently so that protocol cleanup and
  logging semantics are retained.

## Validation

At minimum, inspect the final diff and perform a source-level reachability review using
these two scenarios:

1. In each pre-auth state that can receive decoded packets, a channel-open or subsequent
   capability-bearing request reaches rejection/disconnect and cannot reach command,
   subsystem, shell, or channel execution code.
2. Following a normal completed authentication transition, the same valid channel flow
   reaches its prior handler.

When allowed by the task/runtime, also run the smallest existing SSH-focused test,
compilation, or syntax check that exercises the changed module. Do not claim tests were
run unless they actually were. If no build is requested, report the files changed, the
state boundary selected, the rejected message classes, and the manual reachability checks
performed.

## Failure handling

If no common boundary exists, do not guess at state names. Document the separate dispatch
paths and add equivalent state-aware rejection at each required entry point, retaining one
clearly justified authenticated predicate. If a message is required for authentication,
exclude it from the rejection set and ensure it cannot invoke capability handling. If the
source tree or the SSH module is absent, stop and report that prerequisite rather than
editing unrelated code.
