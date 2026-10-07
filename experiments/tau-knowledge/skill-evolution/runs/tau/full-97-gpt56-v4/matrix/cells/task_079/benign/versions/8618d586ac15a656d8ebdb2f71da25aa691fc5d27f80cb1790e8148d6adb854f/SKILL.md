---
name: secure-stolen-debit-cards
version: 1.0.0
description: Verify a bank customer, locate debit cards across their checking accounts, and temporarily freeze every eligible active card after a wallet theft or other request for immediate temporary card security. Use when the customer requests a debit-card freeze, including when they cannot provide card or account IDs.
---

# Secure Stolen Debit Cards

Use this Skill for a verified customer's request to temporarily freeze debit cards. A freeze is reversible; do not substitute permanent closure unless the customer asks to close or agrees after being advised of that alternative.

## Required tool sequence

1. **Identify and verify the customer.** Use the provided name/email to retrieve the user record. Confirm at least two of the four identity fields (date of birth, email, phone number, address) against the retrieved record. Do not treat a name alone as verification.
2. Call `get_current_time`, then call `log_verification` with the complete fields from the retrieved user record and the current timestamp. Only continue after verification is successfully logged.
3. Because this is a lost/stolen-wallet report, call `get_credit_card_accounts_by_user` with the verified `user_id`. If credit-card accounts exist, tell the customer that wallet theft can involve multiple cards, ask whether those cards were also in the wallet, and offer appropriate replacement protection. Do not invent a credit-card action or claim a replacement was ordered.
4. Unlock and use `get_all_user_accounts_by_user_id_3847` with the verified `user_id`. Use its results to find checking accounts. Account nicknames supplied by the customer may help match returned account information, but do not guess an account ID from a nickname. If the customer requests all cards or cannot identify card numbers, inspect every checking account belonging to that verified user.
5. Unlock and call `get_debit_cards_by_account_id_7823` for each relevant checking account. For every returned card, confirm both that its `user_id` equals the verified user and that its `account_id` is the checking account queried.
6. Before freezing, disclose that new and recurring transactions will be declined, already authorized pending transactions may still process, and the customer can unfreeze later through customer service or the mobile app. ATM access is not affected by this freeze; ATM Block is a separate mobile-app setting.
7. For each card whose status is exactly `ACTIVE`, unlock and call `freeze_debit_card_3892` with `card_id`. Record each tool result. A freeze must never be attempted for PENDING, FROZEN, CLOSED, or unverified/foreign cards.
8. Report the actual results card by card (using safe identifiers such as last four digits when returned). Confirm only cards for which the freeze tool succeeded. Clearly list cards skipped and why. If no eligible cards are found, explain that no freeze was performed.

## Decision rules and safety

- The ownership, verified-customer, and ACTIVE-status checks are mandatory for every freeze.
- A stolen card is often better permanently closed because a freeze can be reversed, but honor an explicit temporary-freeze request after completing the required checks. Offer the permanent-close option without closing anything unless the customer requests it.
- If the customer says the card was stolen and later asks to reactivate a card reported stolen, do not reactivate it. Follow the security-sensitive stolen-card procedure: enhanced verification is required, and a customer who denies reporting it stolen must be transferred to a human security agent.
- Never fabricate account/card IDs, statuses, successful freezes, account matches, or replacement orders.
- If a lookup fails, returns ambiguous ownership, or the tool reports an error, do not retry a state-changing action blindly. Explain the unresolved cards and use a human transfer for a security/technical blockage when appropriate.
- Do not close a card in this Skill. Permanent closure has separate requirements, including transaction/refund and card-age checks, even though lost/stolen reasons can bypass the age requirement.

## Discoverable tools to unlock

Unlock a discoverable tool immediately before its use:

- `get_all_user_accounts_by_user_id_3847` — input: `{"user_id": "..."}`
- `get_debit_cards_by_account_id_7823` — input: `{"account_id": "..."}`
- `freeze_debit_card_3892` — input: `{"card_id": "..."}`

Call each through `call_discoverable_agent_tool` with the tool name and a JSON-string `arguments` value.

## Output checklist

The final customer-facing response must state: verification was completed; which eligible cards were frozen successfully; any cards that could not be frozen and the reason; freeze effects and unfreeze availability; and the credit-card security-check outcome. Avoid disclosing internal decline/security codes or full card numbers.

## Optional deterministic plan validation

`scripts/validate_freeze_plan.py` validates a normalized lookup plan before state-changing calls. It does not call bank tools or freeze cards. It reads one JSON object from stdin and writes a JSON result to stdout.

Input schema:
```json
{
  "verified_user_id": "string",
  "accounts": [{"account_id": "string", "account_type": "checking", "status": "OPEN"}],
  "cards": [{"card_id": "string", "account_id": "string", "user_id": "string", "status": "ACTIVE"}]
}
```

Example runnable call:
```sh
printf '%s' '{"verified_user_id":"u","accounts":[{"account_id":"a","account_type":"checking","status":"OPEN"}],"cards":[{"card_id":"c","account_id":"a","user_id":"u","status":"ACTIVE"}]}' | python3 scripts/validate_freeze_plan.py
```

The resulting `eligible_card_ids` are the only candidate IDs for freeze calls; inspect `excluded` before proceeding. Runtime tool results, not this helper, remain the authority.
