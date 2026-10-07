---
name: fix-erlang-ssh-cve
description: Harden the Erlang/OTP SSH server state machine so unauthenticated SSH connection-protocol messages (channel open / channel request / exec, and the global/channel message family) cannot be dispatched to execution before the connection reaches an authenticated (connected) state. Use when a task provides Erlang/OTP SSH source (e.g. otp_src_27.3.2) and asks to investigate and fix a pre-auth remote-command-execution vulnerability (CVE-2025-32433 class) by editing the source only, without building or running the server.
---

# Fixing the Erlang/OTP SSH pre-authentication command execution bug

## What the task asks

The environment provides affected Erlang/OTP SSH source under `/app/workspace`
(typically `/app/workspace/otp_src_27.3.2`). A remote attacker can execute
system commands **without authentication** by sending crafted SSH connection
protocol messages. You must:

1. Investigate which SSH message type triggers the attack.
2. Fix the bug **inside the provided source only** (no build, no server start).
3. Keep normal authenticated SSH behavior working while blocking the
   unauthenticated capability-bearing messages from reaching execution.

## Root cause (background knowledge applied)

SSH layers transport negotiation, user authentication, and the connection
protocol. Messages that **create channels, request services, or trigger
application behavior** (channel open, channel request / exec, global request,
channel data, etc.) must only be dispatched after the connection has reached
an authenticated state. Packet parsing is not authorization. The vulnerable
handler dispatches these connection-protocol records to
`ssh_connection:handle_msg/...` regardless of the current state-machine state,
so an attacker can open a channel and run an `exec` request before auth.

The fix is small and state-oriented: trace each connection-protocol message
from decode through state dispatch, find the narrowest common authorization
boundary (the `gen_statem` state tuple that distinguishes `{connected, _}`
from pre-auth states), and ensure capability-bearing messages received in any
non-connected state are rejected/disconnected instead of handled.

## Where to look

The dispatch lives in the SSH connection handler, almost always:

```
<root>/lib/ssh/src/ssh_connection_handler.erl
```

States are `gen_statem` tuples like `{hello,Role}`, `{kexinit,Role}`,
`{key_exchange,Role}`, `{new_keys,Role}`, `{service_request,Role}`,
`{userauth,Role}`, `{userauth_keyboard_interactive,Role}`, and
`{connected,Role}`. Connection-protocol messages are Erlang records such as
`#ssh_msg_global_request{}`, `#ssh_msg_channel_open{}`,
`#ssh_msg_channel_request{}`, `#ssh_msg_channel_data{}`,
`#ssh_msg_channel_window_adjust{}`, `#ssh_msg_channel_eof{}`,
`#ssh_msg_channel_close{}`, `#ssh_msg_channel_success{}`,
`#ssh_msg_channel_failure{}`, `#ssh_msg_request_success{}`,
`#ssh_msg_request_failure{}`, `#ssh_msg_channel_open_confirmation{}`,
`#ssh_msg_channel_open_failure{}` (SSH message numbers 80–100).

## Procedure

1. Run `scripts/locate.py` to find the handler file and the `handle_event`
   clauses that dispatch connection-protocol records (and the
   `ssh_connection:handle_msg` call sites). Read the reported ranges with the
   terminal to understand the real clause shapes in this exact source.
2. Identify the authorization boundary: the clause(s) that forward the
   capability-bearing records. In the vulnerable code these match the records
   regardless of the `StateName`/role tuple.
3. Apply a minimal, state-oriented guard so those records are only dispatched
   when the state is `{connected, _}`. Add a preceding clause that, for the
   same record family in any other state, disconnects with a protocol error
   (e.g. `ssh_connection_handler` disconnect helper /
   `SSH_DISCONNECT_PROTOCOL_ERROR`) rather than handling the message.
   - Because Erlang matches clauses top-to-bottom, place the reject/disconnect
     clause **before** the permissive dispatch clause, or add a guard
     (`when StateName =:= {connected, Role}`) to the dispatch clause itself.
   - Do not special-case a single message code or a single packet order:
     cover the whole connection-protocol record family so the fix is not
     bypassable by a different channel/exec message or ordering.
4. Preserve ordinary protocol error handling and all genuinely
   pre-auth-legal messages (transport/kex/service/userauth messages must still
   flow and reach `{connected,_}` normally).
5. See `references/fix-notes.md` for the concrete patch shape and the SSH
   message-number table.

## Verifying (no build required, but check what you can)

Run `scripts/verify.py` against the edited file. It checks, as heuristics
derived from the public requirement, that:
- a connected-state guard now gates the connection-protocol dispatch, and
- a disconnect/reject path exists for those records in non-connected states,
- the file still parses as balanced Erlang (paren/brace/clause sanity), and
- if `erlc`/`erl` is available it attempts a syntax/compile check of the
  single module (best effort; a full OTP build is not required).

Treat verify.py output as advice: open and read the actual diff, confirm
clause ordering and pattern matching, and confirm the `{connected,_}` dispatch
is still reachable (normal authenticated flow preserved) while pre-auth
capability messages hit the disconnect path. If `erlc` is unavailable, rely on
the balance/structure checks plus a careful manual read; do not claim a build
succeeded when it did not.

## Deliverable

An edited `ssh_connection_handler.erl` (and only the minimal related files, if
any) inside the provided source tree implementing the state guard. The task
grades the source change itself — you must actually modify the file, not just
describe it. Do not run or start the server; do not perform a full OTP build.

## Failure handling

- If `ssh_connection_handler.erl` is not found under `/app/workspace`, use
  `scripts/locate.py` with an explicit `root`, or search the tree with the
  terminal; report clearly if the SSH source is absent.
- If the real clause structure differs from the notes, adapt: the invariant to
  enforce is "connection-protocol capability messages dispatch only in
  `{connected, _}`", not a literal text match.
