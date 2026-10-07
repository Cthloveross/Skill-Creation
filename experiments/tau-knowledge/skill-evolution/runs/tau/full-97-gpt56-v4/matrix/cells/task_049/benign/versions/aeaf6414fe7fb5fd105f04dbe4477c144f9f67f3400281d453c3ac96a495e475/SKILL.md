---
name: credit-card-account-closure
version: 1.0.0
description: Safely process a verified customer's request to close one specified Rho-Bank credit card. Use for account-closure requests requiring eligibility checks, optional retention handling, closure-reason logging, and required customer disclosures.
---

# Credit Card Account Closure

Use this Skill for **one explicitly identified card at a time**. Do not infer that a request to close several cards authorizes closure of every card; confirm the next card separately after finishing the current request.

## Required inputs and tools

Obtain at runtime:

- authenticated customer `user_id`;
- selected `credit_card_account_id` and its card type, opening date, balance, and rewards balance;
- current timestamp;
- the customer's closure reason and whether they will consider retention (unless already supplied in the conversation);
- identity verification status.

The process uses these agent-discoverable tools after unlocking them as needed:

- `get_user_dispute_history_7291` with `user_id`;
- `get_pending_replacement_orders_5765` with `credit_card_account_id`;
- `get_closure_reason_history_8293` with `credit_card_account_id`;
- `log_credit_card_closure_reason_4521` with exactly `credit_card_account_id`, `user_id`, and `closure_reason`;
- `close_credit_card_account_7834` with `credit_card_account_id` and `user_id`.

Use `apply_credit_card_account_flag_6147` only for the documented annual-fee waiver retention path; it is not needed merely to close an account.

## Procedure

1. **Identify scope and account.** Locate the user and list their credit-card accounts. Confirm the exact requested card (not just a similarly named card) and confirm that the requester wants this particular card closed.

2. **Verify identity before account action.** Retrieve the profile and ask the customer to confirm at least two of the four profile fields: date of birth, email, phone number, and address. Do not reveal values first. After two fields match, get the current time and call `log_verification` with all required profile fields, the customer name, user ID, and timestamp. If verification fails or remains incomplete, do not log verification, disclose account details, run closure actions, or close the account.

3. **Check closure eligibility immediately before closure/retention.** Review the selected account's balance and opening date, then unlock and call both dispute and replacement-order tools. An account is eligible only if all are true:
   - balance is exactly `$0.00`;
   - it has been open at least 60 calendar days as of the current date;
   - the dispute history has no active/pending dispute for the selected card (treat statuses such as `open`, `pending`, or `under_review` as unresolved; do not assume a user-level dispute belongs to this card without reviewing its transaction/card context);
   - replacement-order results are empty, or every returned order is clearly `delivered` or `cancelled`.

   Customer statements can provide context but do not replace these required system checks. Use `scripts/evaluate_closure_eligibility.py` to evaluate structured tool results consistently. If any requirement is not met, explain the specific blocker and what must be resolved. Do not make retention offers, log a closure reason, or invoke the closure tool.

4. **Determine retention path only after eligibility passes.** Unlock and call `get_closure_reason_history_8293`. If the account has a closure-reason record in the past year, skip retention offers and proceed to reason logging and closure. Otherwise, obtain a reason if not already known, map it to one of the allowed values below, and log it with `log_credit_card_closure_reason_4521` using no extra arguments:
   `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, or `other`.

   If the customer explicitly says they want closure without considering offers, respect that decision: log the known reason and proceed without a retention offer. Never pressure the customer.

   When the customer is willing to discuss retention and has no recent prior attempt, address the stated concern, then make at most one tier-appropriate offer if they still wish to close:
   - entry tier: 500 points or $5 statement credit;
   - mid tier: 2,000 points or $20 statement credit;
   - premium and above: 5,000 points or $50 statement credit.

   For an annual-fee concern, a customer of 2+ years may instead be offered a one-year annual-fee waiver. If accepted, call `apply_credit_card_account_flag_6147` with `flag_type: "annual_fee_waived"`, `reason: "loyalty_benefit"`, and an `expiration_date` exactly one year from today in `MM/DD/YYYY`; do not close unless the customer still requests closure. For shorter tenure, offer a permanent no-annual-fee downgrade rather than inventing an unavailable tool or action.

5. **Close only after all checks and the customer's final decision support closure.** Unlock `close_credit_card_account_7834` and call it with exactly the selected account ID and verified user ID. Treat a tool error or ambiguous result as not closed; do not retry blindly and do not claim success until a successful result is returned.

6. **Give post-closure communication.** On successful closure, state that a confirmation email and final statement will arrive within several business days. Explain that unredeemed rewards remain redeemable for 45 days after the closure request and are then forfeited. If an annual fee posted within 37 days of closure, mention eligibility for a full refund; otherwise do not promise one. Mention a linked Green Account savings bonus may end if the closed card was providing that bonus. For rewards questions, provide only supported options and minimums; do not redeem or transfer points unless a separately authorized available tool supports it.

## Failure handling

- Missing customer, multiple possible cards, missing eligibility data, inaccessible tool, malformed result, or ambiguous dispute/order status: pause closure and obtain clarification or escalate through the normal support path. Do not assume eligibility.
- If a closure reason cannot be mapped confidently, use `other` only when the customer has given a reason that does not fit the listed choices; otherwise ask a focused question.
- Do not close unrelated accounts, disclose sensitive profile values before verification, or represent an unexecuted tool recommendation as a completed bank action.

## Helper usage

`scripts/evaluate_closure_eligibility.py` reads one JSON object from stdin and emits one JSON object on stdout. It performs deterministic eligibility evaluation only; it does not call banking tools or close accounts.

Example input shape:

```json
{
  "current_date": "2025-11-14",
  "date_of_account_open": "2024-03-01",
  "current_balance": "$0.00",
  "disputes": [],
  "replacement_orders": []
}
```

Run it after collecting fresh tool results, inspect `eligible` and `blockers`, and retain the tool results as the operational record. A successful closure workflow requires `eligible: true` before the closure call; script validation errors mean the data must be corrected or re-collected.
