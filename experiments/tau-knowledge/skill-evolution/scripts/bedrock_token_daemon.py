#!/usr/bin/env python3
"""Mint and refresh Bedrock Mantle bearer tokens for many AWS accounts.

Runs under the SYSTEM ``python3`` (3.9) that has ``boto3`` and
``aws_bedrock_token_generator`` installed; it is deliberately independent of
the experiment virtualenv.

For every account the parent process spawns a CHILD process
(``--mint ACCOUNT REGION``) that runs ``ada credentials print`` for that
account, exports the temporary credentials into its own environment and calls
``aws_bedrock_token_generator.provide_token``. ``provide_token`` reads the
default credential chain, so the per-account child isolation is what prevents
one account's token being written under another account's file name.

Output files (``<out-dir>/<account>.json``) are consumed by the experiment via
``AWS_BEARER_TOKEN_BEDROCK_FILE`` and re-read before every request. They are
written atomically (temp file in the same directory + ``os.replace``, mode
0600). ``status.json`` summarises the fleet without any token values.

ada/Midway credentials last one hour, so ``--interval-seconds`` must stay well
under 60 minutes (default 1200 s = 20 min). ada also reuses cached session
credentials, so a mint can return an ``Expiration`` much closer than one hour:
the parent therefore sleeps ``min(interval, soonest_expiry - now - 2*margin)``
and refuses to publish a token that is already within the expiry margin.
Accounts are minted by a small thread pool (``--parallel``) so one hung ``ada``
cannot stretch a cycle past the credential lifetime. On failure the previous
file is kept and the error is logged to stderr; tokens are never logged.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DEFAULT_ADA = "/home/tianrgua/.toolbox/bin/ada"
DEFAULT_ROLE = "IibsAdminAccess-DO-NOT-DELETE"
DEFAULT_PROVIDER = "conduit"
DEFAULT_REGION = "us-east-1"
DEFAULT_INTERVAL_SECONDS = 1200
DEFAULT_PARALLEL = 8
ADA_TIMEOUT_SECONDS = 120
MINT_TIMEOUT_SECONDS = 180
EXPIRY_MARGIN_SECONDS = 60
MIN_SLEEP_SECONDS = 30

_STOP = False


# ----------------------------------------------------------------------------
# pure helpers (imported by tests)
# ----------------------------------------------------------------------------


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_timestamp(value: Any) -> datetime:
    """Parse ISO-8601 (``Z`` or offset); naive values are UTC."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp must be a non-empty ISO-8601 string")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def is_expired(expires_at: Any, now: datetime, margin_seconds: int = EXPIRY_MARGIN_SECONDS) -> bool:
    """True when ``now`` is within ``margin_seconds`` of (or past) ``expires_at``."""
    return now >= parse_timestamp(expires_at) - timedelta(seconds=margin_seconds)


def parse_ada_credentials(text: str) -> dict[str, str]:
    """Parse ``ada credentials print --format json`` (credential_process schema)."""
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        raise ValueError("ada did not return JSON credentials") from None
    if not isinstance(value, dict):
        raise ValueError("ada credentials must be a JSON object")
    required = ("AccessKeyId", "SecretAccessKey", "SessionToken", "Expiration")
    missing = [name for name in required if not isinstance(value.get(name), str) or not value[name]]
    if missing:
        raise ValueError("ada credentials are missing fields: " + ", ".join(missing))
    parse_timestamp(value["Expiration"])
    return {name: value[name] for name in required}


def credential_environment(base: dict[str, str], credentials: dict[str, str], region: str) -> dict:
    """Environment for the token generator: explicit static keys, no AWS_PROFILE."""
    env = dict(base)
    env.pop("AWS_PROFILE", None)
    env.pop("AWS_BEARER_TOKEN_BEDROCK", None)
    env["AWS_ACCESS_KEY_ID"] = credentials["AccessKeyId"]
    env["AWS_SECRET_ACCESS_KEY"] = credentials["SecretAccessKey"]
    env["AWS_SESSION_TOKEN"] = credentials["SessionToken"]
    env["AWS_DEFAULT_REGION"] = region
    env["AWS_REGION"] = region
    return env


def ada_command(ada: str, account: str, role: str, provider: str) -> list[str]:
    return [
        ada,
        "credentials",
        "print",
        "--account",
        account,
        "--provider",
        provider,
        "--role",
        role,
        "--format",
        "json",
    ]


def mint_command(
    script: str, python: str, account: str, region: str, ada: str, role: str, provider: str
) -> list[str]:
    return [
        python,
        script,
        "--mint",
        account,
        region,
        "--ada",
        ada,
        "--role",
        role,
        "--provider",
        provider,
    ]


def build_token_payload(
    account: str, region: str, token: str, expires_at: str, minted_at: str
) -> dict[str, str]:
    for name, value in (
        ("account", account),
        ("region", region),
        ("token", token),
        ("expires_at", expires_at),
        ("minted_at", minted_at),
    ):
        if not isinstance(value, str) or not value:
            raise ValueError("token payload field must be a non-empty string: " + name)
    parse_timestamp(expires_at)
    parse_timestamp(minted_at)
    return {
        "account": account,
        "region": region,
        "token": token,
        "expires_at": expires_at,
        "minted_at": minted_at,
    }


def parse_mint_output(text: str) -> dict[str, str]:
    """Validate the child's stdout: ``{"token": ..., "expires_at": ...}``."""
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        raise ValueError("mint child did not return JSON") from None
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("token"), str)
        or not value["token"]
        or not isinstance(value.get("expires_at"), str)
    ):
        raise ValueError("mint child output is malformed")
    parse_timestamp(value["expires_at"])
    return {"token": value["token"], "expires_at": value["expires_at"]}


def status_entry(
    previous: dict[str, Any] | None,
    *,
    minted_at: str | None = None,
    expires_at: str | None = None,
    error: str | None = None,
    now: str,
) -> dict[str, Any]:
    """Per-account status without token values; failures keep the last success."""
    entry = dict(previous or {"minted_at": None, "expires_at": None, "last_error": None})
    if error is None:
        entry["minted_at"] = minted_at
        entry["expires_at"] = expires_at
        entry["last_error"] = None
        entry["last_success_at"] = now
    else:
        entry["last_error"] = error
        entry["last_failure_at"] = now
    return entry


def next_sleep_seconds(status: dict[str, Any], now: datetime, interval_seconds: int) -> float:
    """Sleep until the configured interval or until the soonest token needs renewal.

    Only accounts whose last mint succeeded count; their ``expires_at`` is what
    ada returned (possibly a cached credential with little lifetime left).
    """
    soonest = None  # type: datetime | None
    for entry in status.get("accounts", {}).values():
        if entry.get("last_error") or not entry.get("expires_at"):
            continue
        expires = parse_timestamp(entry["expires_at"])
        if soonest is None or expires < soonest:
            soonest = expires
    sleep = float(interval_seconds)
    if soonest is not None:
        until_renewal = (soonest - now).total_seconds() - 2 * EXPIRY_MARGIN_SECONDS
        sleep = min(sleep, until_renewal)
    return max(float(MIN_SLEEP_SECONDS), sleep)


def parse_accounts(value: str) -> list[str]:
    accounts = [item.strip() for item in value.split(",") if item.strip()]
    if not accounts:
        raise ValueError("--accounts must list at least one account")
    if len(set(accounts)) != len(accounts):
        raise ValueError("--accounts contains duplicates")
    return accounts


def write_atomic_json(path: Path, payload: dict[str, Any], mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


# ----------------------------------------------------------------------------
# child: mint one token with isolated credentials
# ----------------------------------------------------------------------------


def mint_in_child(account: str, region: str, *, ada: str, role: str, provider: str) -> dict:
    result = subprocess.run(
        ada_command(ada, account, role, provider),
        capture_output=True,
        text=True,
        timeout=ADA_TIMEOUT_SECONDS,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()
        last = detail[-1] if detail else "no stderr"
        raise RuntimeError(f"ada credentials print failed (exit {result.returncode}): {last}")
    credentials = parse_ada_credentials(result.stdout)
    for key, value in credential_environment(dict(os.environ), credentials, region).items():
        os.environ[key] = value
    os.environ.pop("AWS_PROFILE", None)
    from aws_bedrock_token_generator import provide_token

    token = provide_token(region=region)
    if not isinstance(token, str) or not token:
        raise RuntimeError("token generator returned an empty token")
    return {"token": token, "expires_at": credentials["Expiration"]}


# ----------------------------------------------------------------------------
# parent: refresh loop
# ----------------------------------------------------------------------------


def log(message: str) -> None:
    sys.stderr.write(format_timestamp(utc_now()) + " " + message + "\n")
    sys.stderr.flush()


def run_mint_child(account: str, region: str, *, ada: str, role: str, provider: str) -> dict:
    command = mint_command(
        os.path.abspath(__file__), sys.executable, account, region, ada, role, provider
    )
    result = subprocess.run(
        command, capture_output=True, text=True, timeout=MINT_TIMEOUT_SECONDS, check=False
    )
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()
        last = detail[-1] if detail else "no stderr"
        raise RuntimeError(f"mint child failed (exit {result.returncode}): {last}")
    return parse_mint_output(result.stdout)


def _mint_or_error(account: str, region: str, ada: str, role: str, provider: str) -> tuple:
    """Thread-pool body: never raises; tokens stay inside the returned mapping."""
    if _STOP:
        return account, None, "stopped before minting"
    try:
        minted = run_mint_child(account, region, ada=ada, role=role, provider=provider)
        if is_expired(minted["expires_at"], utc_now()):
            raise RuntimeError(
                "ada returned credentials already within the expiry margin "
                f"(expires_at={minted['expires_at']})"
            )
        return account, minted, None
    except Exception as exc:  # noqa: BLE001 - reported per account, never fatal
        return account, None, f"{type(exc).__name__}: {exc}"


def refresh_all(
    accounts: list[str],
    region: str,
    out_dir: Path,
    status: dict[str, Any],
    *,
    ada: str,
    role: str,
    provider: str,
    parallel: int = DEFAULT_PARALLEL,
) -> dict[str, Any]:
    """Mint every account (bounded thread pool); files/status are written here only."""
    accounts_status = status.setdefault("accounts", {})
    workers = max(1, min(parallel, len(accounts)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = pool.map(
            lambda account: _mint_or_error(account, region, ada, role, provider), accounts
        )
        for account, minted, error in results:
            now = format_timestamp(utc_now())
            if error is None and minted is not None:
                try:
                    payload = build_token_payload(
                        account, region, minted["token"], minted["expires_at"], now
                    )
                    write_atomic_json(out_dir / (account + ".json"), payload)
                except (OSError, ValueError) as exc:
                    error = f"{type(exc).__name__}: {exc}"
            if error is None and minted is not None:
                accounts_status[account] = status_entry(
                    accounts_status.get(account),
                    minted_at=now,
                    expires_at=minted["expires_at"],
                    now=now,
                )
                log(f"minted token for account {account} (expires_at={minted['expires_at']})")
            else:
                accounts_status[account] = status_entry(
                    accounts_status.get(account), error=error or "unknown error", now=now
                )
                log(f"FAILED account {account}: {error} (previous token file kept)")
            status["updated_at"] = format_timestamp(utc_now())
            write_atomic_json(out_dir / "status.json", status, mode=0o644)
    return status


def _handle_stop(signum: int, _frame: Any) -> None:
    global _STOP
    _STOP = True
    log(f"received signal {signum}; stopping after the current account")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--accounts", help="comma-separated AWS account IDs")
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--out-dir", type=Path, help="directory for <account>.json token files")
    parser.add_argument("--interval-seconds", type=int, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--once", action="store_true", help="refresh every account once and exit")
    parser.add_argument("--ada", default=DEFAULT_ADA)
    parser.add_argument("--role", default=DEFAULT_ROLE)
    parser.add_argument("--provider", default=DEFAULT_PROVIDER)
    parser.add_argument(
        "--parallel",
        type=int,
        default=DEFAULT_PARALLEL,
        help="accounts minted concurrently (each in its own child process)",
    )
    parser.add_argument(
        "--mint",
        nargs=2,
        metavar=("ACCOUNT", "REGION"),
        help="internal: mint one token in this process and print JSON to stdout",
    )
    args = parser.parse_args(argv)

    if args.mint:
        account, region = args.mint
        try:
            minted = mint_in_child(
                account, region, ada=args.ada, role=args.role, provider=args.provider
            )
        except Exception as exc:  # noqa: BLE001 - botocore/ImportError must be one stderr line
            sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
            return 1
        sys.stdout.write(json.dumps(minted) + "\n")
        return 0

    if not args.accounts or args.out_dir is None:
        parser.error("--accounts and --out-dir are required")
    if args.interval_seconds <= 0 or args.interval_seconds >= 3600:
        parser.error("--interval-seconds must be between 1 and 3599 (ada credentials last 1h)")
    if args.parallel <= 0:
        parser.error("--parallel must be positive")
    accounts = parse_accounts(args.accounts)
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(out_dir, 0o700)

    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)

    status: dict[str, Any] = {
        "region": args.region,
        "interval_seconds": args.interval_seconds,
        "parallel": args.parallel,
        "started_at": format_timestamp(utc_now()),
        "accounts": {},
    }
    while True:
        refresh_all(
            accounts,
            args.region,
            out_dir,
            status,
            ada=args.ada,
            role=args.role,
            provider=args.provider,
            parallel=args.parallel,
        )
        failed = [name for name, item in status["accounts"].items() if item.get("last_error")]
        if args.once:
            return 1 if failed else 0
        if _STOP:
            return 0
        sleep_seconds = next_sleep_seconds(status, utc_now(), args.interval_seconds)
        if sleep_seconds < args.interval_seconds:
            log(f"soonest token renewal in {sleep_seconds:.0f}s; shortening the cycle")
        deadline = time.monotonic() + sleep_seconds
        while not _STOP and time.monotonic() < deadline:
            time.sleep(min(5.0, max(0.0, deadline - time.monotonic())))
        if _STOP:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
