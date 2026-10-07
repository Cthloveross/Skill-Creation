---
name: audit-cash-back-reward-discrepancies
description: Audit posted Silver Rewards Card transactions for likely cash-back discrepancies, calculate whole stored reward points using the documented 4% travel/software and 1% base rates, guide a customer to submit a dispute, and safely support an approved correction.
---

# Audit Cash Back Reward Discrepancies

Use this Skill when a customer questions credit-card cash back and the applicable transaction category, posted status, card type, amount, and recorded reward points are available. It is specifically able to calculate **Silver Rewards Card** transactions from the documented rules. It does not infer merchant categories, promotions, approval status, or rules for other cards.

## Rules encoded by this Skill

For a posted Silver Rewards Card purchase:

- `Travel` and `Software` categories earn 4.0% cash back, represented in the transaction database as **4 points per dollar**.
- All other eligible categories earn the documented 1.0% base cash back, represented as **1 point per dollar**.
- Calculate stored points as `floor(purchase amount × points per dollar)`. Never round to nearest.
- On cash-back cards, 1 stored point represents $0.01 of cash back.
- Returned or refunded transactions are not eligible for a positive reward calculation; rewards reverse when the credit posts.
- Rewards depend on the merchant-submitted category and posting. Do not treat a merchant name as proof of a category.

The 4% rate applies only when the transaction is actually categorized as Travel or Software. For example, a travel-looking merchant with another supplied category must be evaluated at the category supplied by the transaction record, subject to a category review rather than reclassification by the agent.

## Privacy and verification

A full name is only a lookup value, not identity verification. Do not reveal account profile details, transaction history, reward balances, or use account-changing functions solely because a name matched. When the execution context requires identity verification, confirm two of date of birth, email, phone number, and address against the retrieved profile, obtain the current timestamp, and call `log_verification` with all required retrieved profile fields. Do not ask for card numbers or other sensitive card details.

Once the customer is appropriately identified for the context, retrieve their credit-card account and transaction records using the ordinary banking tools. Confirm that the relevant account is a Silver Rewards Card and use only transactions whose final posted status is known from that runtime. A record displayed as `COMPLETED` can be passed as a known final status when that is how the runtime denotes posted transactions.

## Calculate and review

1. Collect only the relevant transaction fields: `transaction_id`, `credit_card_type`, `transaction_amount`, `category`, `status`, and `rewards_earned`.
2. Run `scripts/audit_silver_rewards.py`. Supply `posted_statuses` explicitly; this avoids silently assuming that an arbitrary status means posted.
3. Review each assessment:
   - `assessed` means the script had a supported category, a final status, and a valid amount.
   - `needs_posting_confirmation` means it must not yet be adjudicated.
   - `needs_category_confirmation` means no category was supplied, so the rate cannot be determined.
   - `not_eligible_for_positive_rewards` covers refunded/returned/reversed statuses.
   - `unsupported_card` means this Skill cannot calculate the card's rewards.
4. For `assessed` transactions, compare `expected_points` and `recorded_points`. A nonzero `difference_points` is a likely discrepancy. The script emits both point and dollar representations plus an exact `update_payload` for an approved correction.
5. Explain the result accurately: points are the database representation of cash back, and a likely discrepancy is not an approval or a promise that a correction will be made. Mention that merchant classification and later credits can affect final rewards.

### Script interface

`scripts/audit_silver_rewards.py` reads one JSON object from standard input and emits one JSON object on standard output.

Required input fields:

- `card_type`: the account card type string.
- `posted_statuses`: nonempty list of runtime statuses that have been confirmed to mean posted/final.
- `transactions`: list of transaction objects. Each needs `transaction_id`, `transaction_amount`, `category`, `status`, and `rewards_earned`; `credit_card_type` is optional but, if supplied, must agree with `card_type`.

Amounts may be JSON numbers or dollar strings. Recorded rewards may be an integer/decimal integral value or a string such as a points field returned by the transaction system. Invalid records are returned as `invalid_input` assessments rather than being calculated.

Invoke it through the supplied runtime as `run_skill_script` with relative path `scripts/audit_silver_rewards.py` and an input object assembled from the live transaction records. It requires only the Python standard library and does not access bank systems or make changes.

### Output validation

Before using a calculated result, verify:

- `ok` is true;
- each transaction being discussed has state `assessed`;
- each expected and recorded point value is a nonnegative whole integer;
- `expected_cash_back` equals `expected_points / 100` formatted to two decimals;
- any tool update value is exactly the script's `update_payload.new_rewards_earned`, in `X points` form.

Do not alter a transaction merely because the output shows a mismatch.

## Submit a customer dispute

For each transaction the customer wants reviewed, provide the customer-facing discoverable tool named:

`submit_cash_back_dispute_0589(user_id: str, transaction_id: str)`

Use `give_discoverable_user_tool` to make this tool available to the customer, with the customer’s own `user_id` and the exact selected `transaction_id` in its JSON arguments when the runtime supports prefilled arguments. The customer, not the agent, executes the submission. Confirm the transaction ID with them first. Advise that receipts, invoices, merchant-category context, or promotional expectations may be requested during review. Do not submit the customer tool on their behalf.

If the customer does not select a specific transaction, present only the non-sensitive summary needed for selection and ask which transaction they want reviewed.

## Apply an approved correction only

This section is for an internal follow-up after a dispute is **resolved and approved**; it is not part of merely identifying a discrepancy.

1. Locate the approved resolved dispute in the `cash_back_disputes` data source and identify its exact `transaction_id`. Do not use an `expected_rewards` field in a dispute record as the calculation source.
2. Re-retrieve the transaction and independently rerun the calculation above using the transaction’s category, status, amount, and card type. If a promotion, a changed category, or a card rule is needed but is not established by available evidence, stop and obtain the applicable rule rather than guessing.
3. Unlock `update_transaction_rewards_3847` with `unlock_discoverable_agent_tool`.
4. Invoke it through `call_discoverable_agent_tool` using the exact transaction ID and the script's `update_payload.new_rewards_earned`. Its required argument form is:
   - `transaction_id`: exact transaction identifier
   - `new_rewards_earned`: whole-point string in the form `X points`
5. Re-read the credit-card transaction history and confirm the stored reward value matches the requested whole-point value. Preserve the amount, supplied category, selected rate, floor calculation, and confirmation result in the available internal case record.

If resolved-dispute access, approval, a required rule, or confirmation after the update is unavailable, do not call the update tool. Escalate through the applicable internal support path instead.
