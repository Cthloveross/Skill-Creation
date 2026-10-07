---
name: harden-erlang-ssh-state-dispatch
description: Investigate and minimally fix an Erlang/OTP SSH server flaw where decoded capability-bearing SSH messages can be dispatched before authentication. Use when an OTP source tree must preserve normal authenticated SSH behavior while preventing pre-auth channel, service, or application execution.
---

# Harden Erlang SSH state dispatch

## Purpose

Apply a small, state-oriented source fix for an SSH server that decodes a message and routes it into connection/application handling before authentication is complete. Parsing a packet is not proof that its operation is authorized.

The goal is to ensure capability-bearing messages (especially channel creation and channel/application requests) cannot reach their execution handlers in unauthenticated protocol states, while leaving ordinary protocol error handling and authenticated traffic reachable.

## Inputs

The executor receives an OTP source root. The optional helper accepts JSON on stdin:

```json
{"root":"/path/to/otp-source","terms":["ssh_msg_channel_open","channel_request"]}
```

`root` must be an existing directory. `terms` is optional; omitted terms search for relevant SSH state-machine concepts. The helper writes JSON containing source locations and nearby lines; it does not edit files.

Run it, for example:

```sh
python3 scripts/find_ssh_dispatch.py <<'JSON'
{"root":"/path/to/otp-source"}
JSON
```

## Investigation method

1. Locate the SSH daemon/client connection state machine and follow the exact receive path: binary decoding, decoded SSH message representation, state callback/`handle_event`/`gen_statem` dispatch, and the handler that creates channels or invokes connection/application callbacks.
2. Identify the authentication-complete state or state-data predicate already used by the implementation. Do not infer authorization solely from negotiated transport state or message ordering.
3. Determine which decoded message family is capability-bearing in the actual source. Channel-open messages and channel requests are common candidates, but inspect all clauses that can create a channel, invoke a subsystem/shell/exec command, request a service, or otherwise trigger application behavior.
4. Find the narrowest *common* dispatch boundary shared by those messages before their capability-bearing handlers run. Prefer a state-specific catch-all/guard or a single authorization check at this boundary over separate checks in individual command handlers.
5. Add a clause/check that applies only before authentication and rejects the invalid message using the module's established protocol-error or disconnect convention. Place Erlang clauses before broader matching clauses and preserve expected return tuples/state transitions.
6. Ensure the authenticated state still reaches the original handler unchanged. Do not broadly reject unrelated key exchange, authentication, disconnect, or normal protocol-error traffic unless the existing state machine already requires that behavior.

## Patch constraints

- Edit the supplied source tree only; do not substitute a firewall, packet parser workaround, or an application-command blacklist.
- Keep the change localized to the state machine or its common authorization boundary.
- Reuse existing record fields, message representations, error helpers, logging, and state transition conventions from the target module.
- Check Erlang clause ordering carefully: a generic decoded-message clause ahead of the new invalid-state clause defeats the fix.
- If authentication state cannot be established from the source, stop and report that the required invariant cannot be safely implemented rather than inventing a state name or record field.

## Validation

After editing, inspect the diff and confirm all of the following from source control flow:

1. An unauthenticated capability-bearing decoded message is consumed by the invalid-state rejection path and cannot reach channel/application execution.
2. The same message after authentication still reaches its former dispatch/handler path.
3. The rejection path returns a valid callback result and follows the project’s normal disconnect/protocol-error behavior.
4. No broad clause shadows expected authentication, transport, disconnect, or authenticated connection clauses.
5. If practical in the provided tree, run the narrowest existing SSH unit test, syntax/compile check, or formatter/checker applicable to the edited module. If the task explicitly says not to build or start the server, do not start it; static control-flow validation and a focused existing check are sufficient.

Use `scripts/find_ssh_dispatch.py` before and after the edit to locate all relevant dispatch sites. Its output is an investigation aid, not proof of security; manually trace every reported path that can execute an operation.
