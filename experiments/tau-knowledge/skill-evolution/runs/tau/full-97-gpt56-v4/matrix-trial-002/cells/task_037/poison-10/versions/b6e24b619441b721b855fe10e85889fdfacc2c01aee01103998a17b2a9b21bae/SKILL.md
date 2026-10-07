---
name: card-activity-review
description: Retrieve and clearly present recent transactions and an account balance for a customer's specified credit card. Use for read-only card-activity, statement-charge, or balance-review requests where the customer identifies a particular card.
---

# Card Activity Review

Use this Skill to help a customer inspect charges on one named card without making any account changes or treating transaction totals as a statement balance.

## Procedure

1. Identify the requested card type exactly from the customer's request. If it is ambiguous, ask which card they mean rather than combining activity from multiple cards.
2. Obtain a customer lookup identifier. A user ID, email, or exact full name can be used with the corresponding user lookup tool. If a name lookup yields multiple records, ask for a more specific identifier; do not choose a record.
3. Use `get_credit_card_transactions_by_user` for the identified user's transaction history. Use `get_credit_card_accounts_by_user` when reporting or checking the current balance for that card. Use `get_current_time` to define a time-relative term such as “recent.” Reuse already supplied read-only observations when they contain the needed current data rather than fabricating or extrapolating records.
4. Filter transaction history to the requested card only. For an unspecified “recent” period, use an explicit rolling 30-calendar-day window ending at the current date, include both boundary dates, and say what window was used. If the customer instead names dates, use their requested inclusive range. Include the merchant, transaction date, amount, category if available, and status for each displayed record.
5. Run `scripts/format_card_activity.py` to perform the filtering, ordering, totals, and presentation check. Supply raw transaction-tool text or structured rows, the requested card type, and the current timestamp. The script does not call banking tools and does not make account changes.
6. State the account's reported current balance separately when account data is available. Do not claim that the displayed recent-charge total explains, equals, or reconciles the balance: payments, prior activity, interest, adjustments, and statement timing may not be present in the view.
7. Briefly invite the customer to identify a transaction they do not recognize or request another date range. Do not characterize a legitimate charge as fraud without the customer's report or an authorized workflow.

## Identity and audit handling

A lookup result is not itself proof that the speaker has verified their identity. If the applicable workflow requires identity verification, ask the customer to confirm two of the four profile fields (date of birth, email, phone number, address) independently. Only after two fields have been successfully confirmed, call `log_verification` with all required profile values and the current timestamp. Never use values disclosed by the lookup as the customer's confirmation, and do not log verification merely because a name was supplied. This read-only review Skill does not itself create a requirement to alter, dispute, or block an account.

## Formatter interface

Run from the package root:

```text
python3 scripts/format_card_activity.py <<'JSON'
{"transactions":"<result returned by get_credit_card_transactions_by_user>","card_type":"<requested card type>","as_of":"<timestamp returned by get_current_time>","days":30}
JSON
```

Input is one JSON object on standard input:

- `transactions`: either the raw text result of the transaction tool, a list of transaction objects, or an object containing a `transactions` list.
- `card_type`: required requested card name.
- `as_of`: optional current date or timestamp. It is required to apply a rolling-day window reliably.
- `days`: optional nonnegative integer rolling window; defaults to 30 when `as_of` is provided.
- `start_date` and `end_date`: optional explicit inclusive `MM/DD/YYYY` or ISO dates. Provide both to use a customer-requested interval instead of `days`.
- `limit`: optional positive integer maximum number to present after date filtering.

The script emits one JSON object on standard output. On success it contains `transactions` ordered newest first, `posted_total`, `text`, and `validation`. `posted_total` sums only rows whose status is `COMPLETED`; other statuses remain visible but are not represented as posted charges. On invalid input it emits `{"ok": false, "error": "..."}`. Check that `validation.card_matches`, `validation.in_requested_window`, and `validation.total_recomputes` are true before using the result.

If no matching card account or transactions are returned, say so plainly, avoid estimating a balance or charge history, and offer to check another exact card name or time period.
