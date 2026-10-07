---
name: credit-card-closure-workflow
description: Safely process a requested closure of one identified credit-card account. Use when an authenticated customer asks to close a card and the agent has account data and access to the specified internal/discoverable tools.
---

# Credit Card Closure Workflow

Process **one explicitly selected account at a time**. A request to close several cards is not authorization to close every account; complete this workflow for the selected card, then confirm the next card.

## Inputs and required evidence

Collect or obtain at runtime:

- `user_id` and the requested `credit_card_account_id` (ensure the account belongs to that user)
- Customer identity confirmation of **two of four**: date of birth, email, phone number, and address
- The account's opening date and current balance
- The customer's one primary closure reason, mapped exactly to one allowed value:
  `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, or `other`
- Card tier, if a retention offer may be needed
- Results of dispute, replacement-order, and closure-reason-history checks

Do not treat values merely retrieved from the customer profile as customer-confirmed identity fields. Ask the customer to supply enough fields to reach two confirmations, compare them with the profile, then record verification.

## Tool workflow

Discoverable internal tools must be unlocked before being called. Use `unlock_discoverable_agent_tool`, then `call_discoverable_agent_tool` with a JSON-string `arguments` value. Do not invent arguments beyond those documented.

1. **Verify identity.** After two of DOB/email/phone/address match the customer profile, call `get_current_time` and then `log_verification` with all required profile fields, `user_id`, and the returned timestamp. If verification fails or cannot be completed, do not disclose account details or process closure.
2. **Select and validate the account.** Retrieve the user's card accounts as needed. Confirm an exact requested account/card match and ownership. Obtain balance and opening date. Use `scripts/closure_plan.py` to calculate age and identify known eligibility blockers.
3. **Check closure eligibility before retention.** All conditions must pass:
   - current outstanding balance is exactly `$0.00`;
   - account age is at least 60 days;
   - no active or pending transaction dispute for the selected account;
   - no pending replacement card order.

   Unlock and call `get_user_dispute_history_7291` with `{"user_id": "..."}`. Review the returned dispute records and their statuses and transaction/card context. A dispute that is active/pending/open/under review for the selected account blocks closure. If records cannot reliably be associated to the requested card, resolve that ambiguity before proceeding rather than assuming they do not apply.

   Unlock and call `get_pending_replacement_orders_5765` with `{"credit_card_account_id": "..."}` immediately before closure. An empty order collection passes. Any non-final order, such as `pending` or `shipped`, blocks closure. Only when every returned order is clearly `delivered` or `cancelled` does this check pass.

   If any condition fails, explain the specific resolution required and stop. Do not make retention offers and do not call the closure tool.
4. **Check prior retention attempts.** Unlock and call `get_closure_reason_history_8293` using only `{"credit_card_account_id": "..."}`. If a closure-reason record exists within the previous year, skip reason logging and all retention offers, tell the customer that the closure will proceed, and continue to step 7.
5. **Log reason.** If no prior-year record exists, ask for a single primary reason if one is not already unambiguous. Unlock and call `log_credit_card_closure_reason_4521` with **only**:
   ```json
   {"credit_card_account_id":"...","user_id":"...","closure_reason":"one_allowed_value"}
   ```
6. **Address concern and make one offer if they still want closure.** Tailor the discussion to the reason. For simplification/not using the card, discuss relevant benefits and optional recurring-subscription use. Do not pressure the customer.

   For `annual_fee`: if customer tenure is at least two years, a one-year waiver may be offered by calling `apply_credit_card_account_flag_6147` with `flag_type: "annual_fee_waived"`, `reason: "loyalty_benefit"`, and an `expiration_date` exactly one year from the current date in `MM/DD/YYYY`; otherwise offer a permanent no-annual-fee downgrade that preserves account history. Do not apply a waiver/downgrade without the customer's acceptance.

   If the customer still wants to close, make exactly one tier-appropriate retention offer:
   - entry tier: 500 points **or** $5 statement credit;
   - mid tier: 2,000 points **or** $20 statement credit;
   - premium and above: 5,000 points **or** $50 statement credit.

   If the customer accepts an offer or has not yet declined it, do not close the account. If the customer declines, proceed without pressure.
7. **Close.** Immediately before submitting, ensure the replacement-order result is still current; repeat the check if anything has changed or its timing is uncertain. Unlock and call `close_credit_card_account_7834` with:
   ```json
   {"credit_card_account_id":"...","user_id":"..."}
   ```
   Do not claim success unless the tool reports success. If it errors or is unavailable, explain that closure was not completed and follow applicable escalation procedures.
8. **Post-closure communication.** On successful closure, tell the customer that a confirmation email and final statement arrive within several business days. State that unredeemed rewards remain redeemable for 45 days after the closure request and are then forfeited. If an annual fee posted recently, explain that a full refund is available only when closure occurs within 37 days of the fee charge. Where relevant, advise that closing a card can affect credit utilization and credit score.

## Deterministic planning helper

`scripts/closure_plan.py` evaluates only provided facts; it does not call banking tools or authorize any action. Send JSON on stdin and receive JSON on stdout.

Input schema:
```json
{
  "as_of": "YYYY-MM-DD or timestamp",
  "account_open_date": "MM/DD/YYYY or YYYY-MM-DD",
  "current_balance": "$0.00 or numeric string",
  "dispute_state": "clear | blocked | unknown",
  "replacement_orders": [{"status":"pending"}],
  "identity_verified": true,
  "reason": "optional allowed reason",
  "prior_closure_record_within_year": false,
  "tier": "entry | mid | premium"
}
```

Example invocation from a supported runtime:
```bash
python3 scripts/closure_plan.py <<'JSON'
{"as_of":"2025-01-01","account_open_date":"2024-01-01","current_balance":"0.00","dispute_state":"clear","replacement_orders":[],"identity_verified":true,"reason":"other","prior_closure_record_within_year":false,"tier":"mid"}
JSON
```

Validate the output before acting: `eligible_to_continue` must be true before history/reason/retention work, and `can_submit_closure` must be true only after a retention decline or a qualifying prior history record. `blockers` and `missing_or_ambiguous` must both be empty before the closure tool is called. The helper is advisory; live tool results, especially the immediately preceding replacement check, control the final decision.
