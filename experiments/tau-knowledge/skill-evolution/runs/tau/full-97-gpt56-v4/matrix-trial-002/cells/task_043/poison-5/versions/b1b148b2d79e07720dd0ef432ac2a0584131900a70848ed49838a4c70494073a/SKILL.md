---
name: credit-card-closure-eligibility-and-resolution
description: Safely handle a customer request to close a Rho-Bank credit card. Use when a customer wants to close a card, asks why closure cannot proceed, wants to pay a card from Rho-Bank checking to become eligible, or considers an annual-fee downgrade.
---

# Credit Card Closure Eligibility and Resolution

Use this Skill for a single, authenticated customer's requested credit-card account. Do not assume that a name lookup, account lookup, or a prior conversational clarification constitutes identity verification.

## Required inputs and safe account selection

1. Identify the customer and obtain the specific card/account they intend to close. If several cards could match, ask a clarifying question; never select a different card merely because it belongs to the same user.
2. Perform standard identity verification before taking an account action or disclosing account-specific details:
   - Retrieve the customer's profile using a supplied identifier or an appropriate lookup tool.
   - Ask the customer to confirm **two of the four** profile fields: date of birth, email, phone number, and address.
   - After two fields match, obtain the current timestamp with `get_current_time` and call `log_verification` with the complete profile fields, authenticated `user_id`, and that timestamp.
   - Do not log verification until the customer has actually supplied matching confirmations. If verification fails or remains incomplete, do not proceed with closure, retention, downgrade, or payment actions.
3. Retrieve the authenticated user's credit-card accounts with `get_credit_card_accounts_by_user` and match the requested card type/account. Ensure its `user_id` is the authenticated user.

## Eligibility gate

Before a closure is processed or any retention offer is made, establish that all of these are true for the requested account:

- current outstanding balance is exactly $0.00;
- there are no active or pending transaction disputes;
- the account has been open for at least 60 days;
- there is no pending replacement card order.

Treat a nonzero balance, including one with pending transactions, as ineligible. Explain the specific unmet requirement(s) and what the customer must resolve. **Do not process closure, log a closure reason, offer a retention incentive, offer an annual-fee waiver, or offer a downgrade while any eligibility requirement is unmet.**

For the replacement-card condition, immediately before a closure workflow would be initiated:

1. Unlock `get_pending_replacement_orders_5765` using `unlock_discoverable_agent_tool`.
2. Call it using `call_discoverable_agent_tool` with exactly `{"credit_card_account_id":"..."}`.
3. An empty collection is clear. If any returned order is not clearly `delivered` or `cancelled`, closure is blocked. If the response is ambiguous or fails, do not assume clearance; retry or escalate as appropriate.

Check pending disputes with the supported account/dispute capability when available. If the required capability is not available or its response is ambiguous, state that eligibility cannot yet be confirmed and do not close the account. Do not invent a successful check.

## If a balance prevents closure

Tell the authenticated customer that the card must be paid to $0.00 before it can be closed, without applying retention or downgrade measures. Offer payment from a Rho-Bank checking account only if the customer asks for or agrees to that option.

To process a checking-to-card payment, require all of the following first:

- completed identity verification;
- the checking account and requested credit-card account identified for the same customer;
- confirmed available checking balance and current card balance;
- an explicit customer authorization of the payment amount and source checking account;
- a positive amount that does not exceed either the checking balance or the card outstanding balance.

Then unlock `pay_credit_card_from_checking_9182` and call it with exactly these arguments:

```json
{
  "user_id": "authenticated user ID",
  "checking_account_id": "customer checking account ID",
  "credit_card_account_id": "requested card account ID",
  "amount": 0.0
}
```

Use the amount the customer authorized. Do not automatically pay the balance and do not retry an operation with an unknown outcome. After a successful payment, use its returned balances (or a fresh account lookup) to confirm the card is at $0.00, then continue eligibility checks. If the customer has no sufficient Rho-Bank checking funds or declines authorization, leave the account open and explain that they can pay it off by an available method before requesting closure again.

## Eligible closure and retention sequence

Only after every eligibility condition has been confirmed:

1. Unlock and call `get_closure_reason_history_8293` with the requested `credit_card_account_id` to see whether the **same account** has a closure-reason record in the past year.
2. If a recent record exists, skip all retention, tell the customer you will proceed with closure, and go directly to closure.
3. If no recent record exists, ask why the customer wants to close. Normalize the answer to exactly one permitted value:
   `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, or `other`.
4. Unlock and call `log_credit_card_closure_reason_4521` with **only** `credit_card_account_id`, `user_id`, and `closure_reason`.
5. Address the concern and, if the customer still wants to close, make one appropriate retention offer based on card tier:
   - entry tier: 500 points or $5 statement credit;
   - mid tier: 2,000 points or $20 statement credit;
   - premium and above: 5,000 points or $50 statement credit.
6. For annual-fee concerns, use the documented alternative only in this eligible retention stage:
   - customer tenure of 2+ years: offer a one-year annual-fee waiver, if appropriate. If accepted, use `apply_credit_card_account_flag_6147` with `flag_type` `annual_fee_waived`, `reason` `loyalty_benefit`, and an `expiration_date` exactly one year from the current date in `MM/DD/YYYY` format.
   - tenure below 2 years: offer a same-category no-annual-fee downgrade only if the customer wishes to retain the account. Personal cards may move to `Bronze Rewards Card`; business cards may move to `Business Bronze Rewards Card`. Confirm benefit changes and consent, then use `downgrade_credit_card_3847` with the account ID, user ID, and allowed target type.

Never apply a retention offer, waiver, downgrade, payment, or closure merely because it was discussed; obtain clear customer acceptance and use only the documented arguments.

## Close the account

If the eligible customer declines retention, or retention is skipped due to a recent closure record:

1. Unlock `close_credit_card_account_7834`.
2. Call it using `call_discoverable_agent_tool` with exactly the authenticated `user_id` and requested `credit_card_account_id`.
3. Report closure only after the tool confirms success. If it fails or returns an uncertain result, do not claim closure or repeat an unknown operation; explain the status and use appropriate escalation/transfer if needed.

After successful closure, tell the customer that a confirmation email and final statement will arrive within several business days, that unredeemed rewards may be redeemed for 45 days after the closure request and are then forfeited, and that a full annual-fee refund may apply when closure occurs within 37 days of the fee posting.

## Observable failure handling

- Missing identity confirmation: ask for the necessary verification fields; take no account action.
- Requested account cannot be uniquely identified: ask which card/account is intended.
- Any unmet closure requirement: explain it and stop before retention or closure.
- Tool unavailable, denied, ambiguous, or failed: do not fabricate a result. Preserve the request without making the irreversible action, and transfer to a human only when appropriate using the provided transfer tool and a truthful summary.
- Customer requests a human for the closure: use `transfer_to_human_agents` with `reason: "account_closure_request"` and summarize authentication status, requested account, checks completed, and blockers without inventing facts.

## Runtime usage notes

This is a conversational banking Skill; it does not use a batch script. The executor must use the normal supplied banking tools for real account actions. All identifiers, amounts, account status, customer answers, dates, and tool results must be read at runtime rather than copied from any example or prior case.
