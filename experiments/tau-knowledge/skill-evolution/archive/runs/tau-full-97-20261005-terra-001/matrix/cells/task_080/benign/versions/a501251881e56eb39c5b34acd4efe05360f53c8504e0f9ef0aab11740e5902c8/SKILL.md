---
name: stolen-wallet-card-security
description: Securely handles a verified customer's report that a wallet containing debit and credit cards was stolen. Use this Skill to locate and temporarily freeze requested debit cards, communicate the documented limits of a debit-card freeze, and handle credit-card protection through the documented replacement workflow when no supported credit-card freeze action is available.
---

# Stolen Wallet Card Security

## Scope and safety boundary

Use this Skill when a customer reports a lost or stolen wallet and requests action on debit cards, credit cards, or both.

A debit-card **freeze** is temporary and is appropriate only when the verified cardholder elects it. A stolen card is also a reason to recommend permanent debit-card closure. Do not substitute closure for a clearly requested temporary freeze, but explain that closure is the safer permanent option for a confirmed theft.

The supplied procedures document `freeze_debit_card_3892` for debit cards. They do **not** document a credit-card freeze tool. Never invent a credit-card lock/freeze action or claim that a credit card has been frozen. For a stolen credit card, offer the documented credit-card replacement process; it cancels the old card when the replacement is submitted.

## Required verification

1. Locate exactly one customer profile using a customer-provided identifier.
2. Verify at least two of the four profile fields: date of birth, email, phone number, and address. Compare what the customer supplies to the retrieved profile; do not treat a profile lookup alone as verification.
3. Obtain a current timestamp with `get_current_time` and call `log_verification` after successful verification. Populate every required logging field from the canonical retrieved profile, including the timestamp and user ID.
4. If there is no unique match or fewer than two fields match, do not retrieve card details for action and do not perform a card action. Request the missing verification information.

Previous read-only observations from the current interaction may be reused only if they establish one unambiguous profile and show two matching customer-provided verification fields. Still create the required verification log before any state-changing action.

## Debit-card workflow

1. Treat the theft report as the reason already requested by the debit-card procedure. State that permanent closure is recommended for a stolen card, while a freeze remains temporary and can later be reversed. The customer's explicit request for a freeze is sufficient to proceed with the temporary-freeze path after this disclosure.
2. Before submitting a freeze, tell the customer:
   - New transactions and recurring payments/subscriptions will be declined while the card is frozen.
   - Pending transactions that were already authorized can still process.
   - The card can be unfrozen through customer service or the mobile app.
   - A debit-card freeze does not itself block ATM access for someone with the PIN; ATM Block must also be enabled separately in the mobile app.
3. Call `get_all_user_accounts_by_user_id_3847(user_id)`. Restrict the target set to the customer's checking accounts. Match each account the customer named using returned account labels/classes, not a guessed account ID. If a name is ambiguous or absent, present the matching account descriptions and ask which one is intended.
4. For every selected checking account, call `get_debit_cards_by_account_id_7823(account_id)`.
5. Select a card only when its `user_id` equals the verified user and its status is exactly `ACTIVE`. If an account has multiple active cards, identify them by last four digits and obtain the customer's selection. Do not freeze a `PENDING`, `FROZEN`, or `CLOSED` card; explain its current status instead.
6. Call `freeze_debit_card_3892(card_id)` once for every eligible, selected debit card. If the runtime exposes these documented names as discoverable agent tools, unlock the named tool before calling it; otherwise use the runtime's normal direct invocation mechanism. Unlocking is not a card action.
7. Confirm success only for card calls that returned success. If an individual call fails, do not describe it as frozen; retain the other confirmed successes and escalate the unresolved security issue through the normal banking support path.

Do not use the debit-card closing tool merely because closure was recommended. If the customer instead chooses closure, follow the separate closure requirements, including pending transaction/refund and card-age checks; lost or stolen closures bypass only the minimum-card-age requirement.

## Credit-card workflow

For every active credit-card account on the verified user's profile:

1. Identify the requested card(s) by returned card type and last four digits. The lost/stolen debit-card cross-product protocol requires proactively offering credit-card replacement protection.
2. Explain that the available documented protection is replacement with a new number, not a documented agent-side credit-card freeze. Ask whether that credit card was in the stolen wallet and whether the customer wants a replacement.
3. Do not submit a replacement until the customer explicitly agrees and all replacement prerequisites are complete:
   - verify identity;
   - confirm the credit-card account;
   - confirm the shipping address, including unit/suite if applicable;
   - record exactly one reason (`fraud_suspected`, `lost`, `stolen`, `damaged`, `expired`, or `other`);
   - obtain a shipping choice: standard (7–10 business days, free) or expedited (2–3 business days);
   - when expedited has a tier fee, obtain fee consent;
   - confirm replacement eligibility, including no pending replacement and the applicable 60-day tier limit.
4. For a qualified, consented request, unlock and call `order_replacement_credit_card_7291` with the account/card identifier, reason, confirmed shipping address, shipping speed, any required expedited-fee acknowledgement, and relevant notes. A submitted replacement automatically cancels the old credit card. Report only the tool's actual result.
5. If an immediate credit-card lock is required but no supported lock action is available, offer or perform escalation using the normal human-transfer process with the security/fraud concern reason. Do not delay the completed debit-card freezes.

For stolen or suspected-fraud credit cards, recommend expedited shipping and review of recent transactions for unauthorized activity. Do not characterize ordinary listed transactions as fraud without the customer's report.

## Tool availability and failure handling

- Use only tool names and arguments documented by the available knowledge and runtime schemas.
- If a documented debit lookup/action tool cannot be accessed after the runtime's normal unlock/direct-call process, explain that the security action could not be completed, preserve any confirmed actions, and escalate rather than guessing IDs or using a different tool.
- If card lookup returns no eligible card, report that specific result and do not claim completion.
- Never process an account or card whose ownership cannot be matched to the verified user.
- Complete independent debit-card freezes even if a different requested card is ambiguous, ineligible, or has a tool failure, as long as the selected cards are unambiguous and eligible.

## Optional deterministic planning helper

`scripts/plan_debit_freezes.py` converts already retrieved *structured* account and debit-card records into a conservative selection plan. It performs no banking action and does not parse tool prose. Run it as:

```text
python3 scripts/plan_debit_freezes.py < request.json
```

Input JSON schema:

```text
{
  "verified_user_id": "string",
  "requested_debit_account_labels": ["string"],
  "accounts": [{"account_id":"string", "account_type":"CHECKING", "account_class":"string", "status":"string"}],
  "debit_cards": [{"card_id":"string", "account_id":"string", "user_id":"string", "status":"ACTIVE", "card_number_last_4":"string"}]
}
```

`account_name`, `display_name`, or `name` may be supplied instead of `account_class`. The output contains `freeze_card_ids`, `selected_cards`, and `blockers`. Execute freezes only for the returned IDs after the required customer disclosure and verification log. A nonempty `blockers` list must be resolved or communicated; never override it by guessing.

## Customer-facing completion

Summarize separately: each debit card successfully frozen, cards not acted on and why, the continuing effect of pending transactions, recurring-payment declines, ATM Block limitation, the permanent-closure option for theft, and the status of each credit-card replacement offer or order. Do not say that all cards are secured unless each requested card has a confirmed, supported outcome.
