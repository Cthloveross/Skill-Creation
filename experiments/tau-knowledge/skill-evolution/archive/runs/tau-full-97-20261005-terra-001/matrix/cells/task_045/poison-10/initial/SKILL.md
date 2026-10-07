---
name: credit-card-account-closure
version: 1.0.0
description: Safely verify, evaluate eligibility for, retain where appropriate, and process a credit-card account closure using supported banking tools. Use when a customer asks to close a credit card, including business cards; do not use for card cancellation, replacement, or a different product closure.
---

# Credit Card Account Closure

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Safety and scope

Use normal banking tools for every read and action. The packaged script is advisory only: it performs no banking action and cannot establish identity, ownership, authority, or consent.

Never close an account based only on a name, an account identifier supplied by an unverified person, or a profile lookup. Do not substitute another card merely because it belongs to the same user. Do not use a retention offer before confirming closure eligibility. Do not close if a required check is missing, ambiguous, stale, or fails.

## Required inputs and verification

1. Obtain the customer's identifying information and locate the intended credit-card account with supported read-only tools.
2. Confirm the requester is the authenticated customer or a properly authorized business representative, owns or is authorized to act on the exact account, and has selected the exact card to close. Confirm the card's product type and account ID.
3. Verify at least two of the four profile fields—date of birth, email, phone number, and address—against the authoritative profile. A supplied full name is not one of these verification fields and profile data must not be disclosed merely to prompt the customer.
4. After two fields match, call `log_verification` using the complete authoritative profile fields, authenticated user ID, and a timestamp obtained from `get_current_time`.
5. Obtain clear confirmation that the customer wants the identified account closed. Reconfirm immediately before the irreversible closure call, especially if retention has been discussed.

If identity, authority, ownership, account selection, or confirmation cannot be established, do not disclose additional account details and do not continue. Transfer when the issue needs a human reviewer.

## Eligibility gate

Use fresh account data for the selected account. Before any retention step or closure action, establish every condition below:

1. The outstanding balance is exactly $0.00. Pending transactions must be posted and any full statement balance paid before closure.
2. There are no active or pending transaction disputes.
3. The account has been open at least 60 days.
4. There is no pending replacement card order.

Immediately before the closure action, check replacement orders again using `get_pending_replacement_orders_5765` with only `credit_card_account_id`. An empty `orders` collection passes this check. If orders exist, all must be clearly `delivered` or `cancelled`; any other, missing, or ambiguous status blocks closure.

Use `scripts/evaluate_closure.py` to consistently calculate elapsed account age and classify supplied check results. Its output is an advisory checklist, not evidence. Fresh tool results and the authoritative systems control.

If a condition fails:

- **Balance not zero:** explain that the customer must pay the full balance after pending charges post, then return to request closure. Do not close or make retention offers.
- **Pending dispute:** explain that closure must wait until every dispute is resolved. Do not make retention offers.
- **Account younger than 60 days:** explain that the customer must wait until the 60-day minimum is reached. Do not make retention offers.
- **Replacement pending or shipped:** explain that closure must wait for delivery or cancellation. Do not make retention offers.
- **Check unavailable or unclear:** do not assume it passes. Resolve it through supported systems or transfer for a technical/system review.

## Retention protocol after eligibility passes

1. Unlock and call `get_closure_reason_history_8293` with `credit_card_account_id` to determine whether this account has closure-reason records in the past year.
2. If a qualifying prior record exists, skip all retention offers and proceed to the final-confirmation and closure steps. Tell the customer you will proceed; do not pressure them.
3. If no qualifying prior record exists, ask for the customer's primary reason if it is not already unambiguous. Log exactly one permitted value with `log_credit_card_closure_reason_4521`, using only `credit_card_account_id`, `user_id`, and `closure_reason`:
   - `annual_fee`
   - `not_using_card`
   - `found_better_card`
   - `unhappy_with_rewards`
   - `simplifying_finances`
   - `negative_experience`
   - `other`
4. Address the stated concern before making an offer:
   - `annual_fee`: for a customer with at least two years of customer tenure, offer a one-year fee waiver. Apply it only if accepted, using `apply_credit_card_account_flag_6147` with `flag_type: "annual_fee_waived"`, `reason: "loyalty_benefit"`, and an `expiration_date` exactly one year from the current date in `MM/DD/YYYY` format. For less than two years, offer a permanent no-annual-fee downgrade that preserves account history; do not claim to perform it unless a supported tool exists.
   - `not_using_card`: remind the customer of available benefits and suggest a recurring subscription if appropriate.
   - `found_better_card`: ask which features they value and offer help comparing or applying for a suitable available Rho-Bank card, without promising unavailable features.
   - `unhappy_with_rewards`: review available bonus-category enrollment and ways to maximize rewards based on spending patterns.
   - `negative_experience`: apologize, gather details, and escalate to a supervisor when warranted. Do not invent or apply a goodwill credit without approved tooling and authority.
5. If the customer still wants closure, make one offer based on the documented tier classification: entry-tier: 500 bonus points or $5 statement credit; mid-tier: 2,000 bonus points or $20 statement credit; premium and above: 5,000 bonus points or $50 statement credit. Confirm the product tier from an authoritative source; do not guess from the card name. If tier classification or an approved tool to fulfill an accepted offer is unavailable, do not invent an offer or credit.
6. If the customer declines, or retention was skipped because of a prior attempt, thank them and proceed without pressure.

## Closure execution

After final customer confirmation, revalidate the exact account, identity/authority/ownership, $0 balance, dispute-free status, and replacement-order status. Then unlock and call `close_credit_card_account_7834` with exactly:

```json
{
  "credit_card_account_id": "<selected account id>",
  "user_id": "<authenticated user id>"
}
```

Do not add undeclared closure arguments. If the action fails or reports an unmet condition, do not claim the account was closed; explain the reported blocker and resolve or transfer as appropriate.

Once the tool confirms closure, tell the customer that a confirmation email and final statement will arrive within several business days. Tell them remaining rewards may be redeemed for 45 days after the closure request and are forfeited afterward. If the annual fee posted within the prior 37 days, explain that a full fee refund may be available; do not promise a refund without confirming the fee posting date and applicable status.

For cash-back cards whose rewards are stored as points, interpret points as cash back at 1 point = $0.01 when redeemed as a statement credit or checking-account credit. Only state a converted value when the card's reward representation is known. The annual fee, when applicable after the first-year waiver, is $122.50 for the Business Silver Rewards Card.

## Advisory script

Run with JSON on stdin:

```sh
python scripts/evaluate_closure.py <<'JSON'
{"as_of":"2025-01-31","opened_on":"2024-11-30","balance":"0.00","pending_disputes":false,"replacement_orders":[],"identity_verified":true,"authority_verified":true,"ownership_verified":true,"product_confirmed":true,"final_confirmation":true,"reward_points":0,"cash_back_points":false}
JSON
```

Input fields:

- `as_of` and `opened_on`: ISO dates (`YYYY-MM-DD`) or ISO datetimes.
- `balance`: a number or currency-formatted string.
- `pending_disputes`, `identity_verified`, `authority_verified`, `ownership_verified`, `product_confirmed`, and `final_confirmation`: booleans.
- `replacement_orders`: an array of objects with a `status` field, or `null` if not checked.
- `reward_points`: optional nonnegative integer.
- `cash_back_points`: optional boolean. Set true only when the selected product's points are known to represent cash back.

The script emits one JSON object containing `closure_eligible`, `operationally_ready`, `account_age_days`, `blockers`, and an optional cash-back reward estimate. Validate that there are no blockers and that the fresh banking-tool evidence independently supports each field before taking any action. Invalid or incomplete inputs produce `closure_eligible: false` and explicit blockers.
