# CVE-2025-32433 class fix notes: Erlang/OTP SSH pre-auth RCE

## Vulnerability summary

The Erlang/OTP SSH server dispatches SSH **connection protocol** messages
(channel open, channel request/exec, global request, channel data, etc.)
through its `gen_statem` handler without first checking that the connection
has completed user authentication. A remote attacker can therefore send a
channel-open followed by a channel-request `exec` **before authenticating**
and have the server run system commands.

The attack-triggering messages are the connection-protocol records (SSH
message numbers 80–100). The actual command execution happens when a
`SSH_MSG_CHANNEL_REQUEST` with an `exec`/`shell`/`subsystem` request reaches
`ssh_connection:handle_msg/...` while the state machine is still pre-auth.

## SSH message numbers (connection protocol)

| Code | Message | Erlang record |
|------|---------|---------------|
| 80 | GLOBAL_REQUEST | `#ssh_msg_global_request{}` |
| 81 | REQUEST_SUCCESS | `#ssh_msg_request_success{}` |
| 82 | REQUEST_FAILURE | `#ssh_msg_request_failure{}` |
| 90 | CHANNEL_OPEN | `#ssh_msg_channel_open{}` |
| 91 | CHANNEL_OPEN_CONFIRMATION | `#ssh_msg_channel_open_confirmation{}` |
| 92 | CHANNEL_OPEN_FAILURE | `#ssh_msg_channel_open_failure{}` |
| 93 | CHANNEL_WINDOW_ADJUST | `#ssh_msg_channel_window_adjust{}` |
| 94 | CHANNEL_DATA | `#ssh_msg_channel_data{}` |
| 95 | CHANNEL_EXTENDED_DATA | `#ssh_msg_channel_extended_data{}` |
| 96 | CHANNEL_EOF | `#ssh_msg_channel_eof{}` |
| 97 | CHANNEL_CLOSE | `#ssh_msg_channel_close{}` |
| 98 | CHANNEL_REQUEST | `#ssh_msg_channel_request{}` |
| 99 | CHANNEL_SUCCESS | `#ssh_msg_channel_success{}` |
| 100 | CHANNEL_FAILURE | `#ssh_msg_channel_failure{}` |

Transport (1–49) and user-auth (50–79) messages are legitimately handled
before `{connected,_}` and must keep working.

## File and state model

- File: `lib/ssh/src/ssh_connection_handler.erl` under the OTP source root
  (e.g. `/app/workspace/otp_src_27.3.2/lib/ssh/src/ssh_connection_handler.erl`).
- `gen_statem` states are `{StateName, Role}` tuples. Pre-auth state names
  include `hello`, `kexinit`, `key_exchange`, `key_exchange_dh_gex_init`,
  `new_keys`, `service_request`, `userauth`,
  `userauth_keyboard_interactive`. The authenticated state is
  `{connected, Role}` (Role is `server`/`client`).
- Decoded messages are dispatched via `handle_event(internal, Msg, StateName, D)`
  clauses; the connection-protocol records are eventually forwarded to
  `ssh_connection:handle_msg(...)`.

## The fix: state-gated dispatch

Enforce the invariant: **connection-protocol capability records are dispatched
only in `{connected, _}`**; in any other state they cause a protocol-error
disconnect. Because Erlang evaluates `handle_event/4` clauses top-to-bottom,
either:

1. Add a guard to the permissive clause so it only matches when connected, and
2. Add a preceding clause that matches the same record family in non-connected
   states and disconnects.

Example shape (adapt names/arity to the real source — do not paste blindly):

```erlang
%% Reject connection-protocol messages that arrive before authentication.
handle_event(internal, Msg, StateName, D)
  when StateName =/= {connected, server},
       StateName =/= {connected, client},
       is_record(Msg, ssh_msg_global_request)   orelse
       is_record(Msg, ssh_msg_request_success)  orelse
       is_record(Msg, ssh_msg_request_failure)  orelse
       is_record(Msg, ssh_msg_channel_open)     orelse
       is_record(Msg, ssh_msg_channel_open_confirmation) orelse
       is_record(Msg, ssh_msg_channel_open_failure)      orelse
       is_record(Msg, ssh_msg_channel_window_adjust)     orelse
       is_record(Msg, ssh_msg_channel_data)     orelse
       is_record(Msg, ssh_msg_channel_extended_data) orelse
       is_record(Msg, ssh_msg_channel_eof)      orelse
       is_record(Msg, ssh_msg_channel_close)    orelse
       is_record(Msg, ssh_msg_channel_request)  orelse
       is_record(Msg, ssh_msg_channel_success)  orelse
       is_record(Msg, ssh_msg_channel_failure) ->
    %% Use the module's existing disconnect helper / macro.
    ssh_connection_handler:disconnect(
        #ssh_msg_disconnect{code = ?SSH_DISCONNECT_PROTOCOL_ERROR,
                            description = "Connection protocol message "
                                          "before authentication"},
        StateName, D);
```

Notes on adapting:
- Guard syntax: a multi-record guard must combine `is_record(...)` tests with
  `orelse`, and the whole record-family test must be parenthesised when mixed
  with the `=/=` state tests via `,`/`andalso`. Match the project's existing
  guard style; if clearer, split into one clause per record or match the
  records in the clause head pattern instead of using `is_record` guards.
- Prefer the module's real disconnect/error helper (grep for `disconnect`,
  `?SSH_DISCONNECT_PROTOCOL_ERROR`, or how other invalid-state messages are
  rejected) so the reject path matches existing conventions.
- Place this clause **before** the clause that forwards these records to
  `ssh_connection:handle_msg`, or add `when StateName =:= {connected, Role}`
  to that forwarding clause so it no longer matches pre-auth states.
- Keep the change minimal and do not alter transport/kex/userauth handling.

## Why not patch a single message

Blocking only `exec`, or only `channel_request`, or only one packet ordering,
leaves the vulnerability reachable through another connection-protocol message
or a different sequence. Gate the whole connection-protocol record family on
the authenticated-state boundary.

## Verification without building the server

A full OTP build is not required. Confirm:
- The authenticated `{connected,_}` dispatch path is still present and
  reachable (normal SSH behavior preserved).
- Pre-auth capability records now hit a disconnect/reject clause.
- Clause ordering, pattern matching, return-state transitions, and syntax are
  correct (balanced parens/braces, proper `;`/`.` clause terminators).
- If `erlc` exists, a syntax check of the module is a useful smoke test
  (missing-include warnings are expected for a single-module compile and are
  not failures). Otherwise review the diff carefully by hand.
