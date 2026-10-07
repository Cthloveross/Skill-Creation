---
name: secure-lost-or-stolen-debit-cards
description: Secure a verified customer's debit cards across named checking accounts. Use for temporary freezes, or confirmed lost/stolen cards requiring permanent closure and requested replacements.
---

# Lost/Stolen Debit-Card Security Workflow

A **freeze** is reversible. A **closure** is permanent and is the safer recommendation once a card is confirmed lost or stolen.

## Mandatory controls

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

Do not infer verification from profile information visible to the agent. Locate the customer by supplied full name or email, then require matching customer-supplied values for **two** of: date of birth, email, phone number, or address. A name only locates a profile. Resolve ambiguity or a mismatch before proceeding. On two matches, obtain `get_current_time` and call `log_verification` with every returned profile field, user ID, and timestamp.

For every card action establish that the account is a requested checking account owned by the verified user, card linkage matches the account, and `card.user_id` matches the verified user. Retrieve the card immediately before acting. Never act on malformed, duplicate, or unverified card IDs; never call an action again after an UNKNOWN result.

## Locate cards

1. Unlock/call `get_all_user_accounts_by_user_id_3847` with the verified user ID. Uniquely match each customer-provided label from returned account label/name/level/class fields. Do not guess between labels or act on non-checking/non-owned accounts.
2. Unlock/call `get_debit_cards_by_account_id_7823` for each matched account. Check linked account ID, user ID, status, and last four digits. Historical cards can be included.
3. Optionally run `scripts/build_freeze_plan.py` to make a non-executing plan; validate every result against the retrieved data.

## Temporary freeze

Before freezing, explain that new purchases and recurring payments/subscriptions will decline; already-authorized pending transactions can still process; and a card can be unfrozen via customer service or the mobile app. A freeze does not block ATM access for someone with the PIN; ATM Block is separately enabled in the mobile app.

Only exactly `ACTIVE` cards are eligible. Unlock `freeze_debit_card_3892` and call it once per unique eligible card with `{"card_id":"..."}`. Do not freeze `PENDING`, `FROZEN`, or `CLOSED` cards. Report those separately and confirm only successful responses. For a lost/stolen report, recommend permanent closure but honor a clear temporary-freeze request.

## Confirmed lost/stolen: close permanently

If the customer later confirms a card is gone and asks to close it, recheck its state and use the closure steps only when all closure requirements are met.

1. Obtain clear confirmation of the cards and reason (`stolen` for a stolen wallet), and tell the customer closure cannot be reversed, recurring merchants need updated details, and pending authorized transactions can still settle.
2. Recheck eligibility. Closure needs an owned `ACTIVE` or `PENDING` card, no pending/processing transactions, and no pending refunds unless the customer supplies the required written acknowledgement that the refund will credit the linked checking account. The 14-day card-age rule is bypassed for `lost`, `stolen`, and `fraud_suspected`. Do not close an ineligible card.
3. Do **not** unfreeze or reactivate a card reported stolen merely to make it closure-eligible. A `FROZEN` card cannot be closed by this procedure because closure needs `ACTIVE` or `PENDING`; preserve the security lock and transfer the customer to the security team with reason `fraud_or_security_concern` for secure permanent-closure handling. Never claim it was closed.
4. For an eligible `ACTIVE` or `PENDING` card, unlock `close_debit_card_4721`; inspect its exposed schema and call it once with `card_id`, confirmed reason, and no invented parameters. A rejected response means no closure. Confirm successes and separately name cards not changed and why.

## Requested replacement after successful closure

Ask whether the customer wants a replacement for each successfully closed card; do not order automatically. Retrieve account/card history and determine the actual tier, count only prior-12-month cards whose issue reason is `lost`, `stolen`, `fraud`, or `damaged`, obtain permitted shipping and design choices, disclose the exact fee, confirm the order, and ensure the linked checking balance supports the fee. Never infer tier or customer choices from a nickname.

Applicable delivery, design, and excess-replacement fees are automatically charged at ordering. Rules:

| Tier | limit/wait | permitted shipping | design fees |
|---|---|---|---|
| ENTRY | 2/year; wait 48 hours after close; excess $25 or wait | STANDARD $0 | CLASSIC $0, PREMIUM $10, CUSTOM $25 |
| MID | 3/year; no wait; excess $15 or wait | STANDARD $0, EXPEDITED $15 | CLASSIC $0, PREMIUM $10, CUSTOM $25 |
| PREMIUM | 5/year; no wait; must wait at limit | STANDARD/EXPEDITED $0, RUSH $35 | CLASSIC/PREMIUM $0, CUSTOM $15 |
| ELITE | unlimited; no wait | STANDARD/EXPEDITED/RUSH $0 | CLASSIC/PREMIUM/CUSTOM $0 |

If any tier, history, choice, fee, balance, or required confirmation is unavailable, do not order. Otherwise unlock `order_debit_card_5739`, inspect its exposed schema, and use the successfully closed card's linked account, confirmed choices, and exact `delivery_fee`/`design_fee` required by that schema. Never invent a parameter. Confirm only successful orders. `scripts/build_replacement_quote.py` can quote explicit inputs but never authorizes an order.

## Lost-wallet cross-product check

After the requested freeze or closure, call `get_credit_card_accounts_by_user`. If cards exist, explain wallet theft may compromise them, ask whether they were in the wallet, and offer a replacement with a new number. If none exist, say no offer applies. Do not disclose internal fraud codes or reactivate a reported stolen card.

## Scripts and validation

Scripts read one JSON object on stdin and write one JSON object on stdout; neither acts on the bank. `build_freeze_plan.py` takes `user_id`, `requested_account_labels`, `accounts`, and account-keyed `cards_by_account`, returning `freeze_actions`/`not_actionable`. Require a unique nonempty ID, exact `ACTIVE`, matching account/user IDs, and a unique requested checking account before acting.

`build_replacement_quote.py` takes `tier` (`ENTRY`/`MID`/`PREMIUM`/`ELITE`), `replacement_count_last_12_months`, `shipping_method`, `card_design`, and, for ENTRY, `closed_at`/`now` ISO dates. It returns eligibility, delivery/design/excess fees, and reasons. Validate against retrieved records, balance, customer confirmation, and tool schema before ordering.

```sh
python3 scripts/build_freeze_plan.py <<'JSON'
{"user_id":"u","requested_account_labels":["A"],"accounts":[{"account_id":"a","class":"checking","level":"A"}],"cards_by_account":{"a":[{"card_id":"c","account_id":"a","user_id":"u","status":"ACTIVE"}]}}
JSON
python3 scripts/build_replacement_quote.py <<'JSON'
{"tier":"MID","replacement_count_last_12_months":1,"shipping_method":"EXPEDITED","card_design":"CLASSIC"}
JSON
```
