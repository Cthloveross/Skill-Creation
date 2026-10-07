---
name: credit-card-rewards-discrepancy-review
description: Review a verified customer's completed credit-card transactions against documented reward rules, calculate whole-point expectations with truncation, explain cash-back point value, and provide the required customer-initiated cash-back dispute tool when a supported discrepancy is found.
---

# Credit-card rewards discrepancy review

Use this Skill when a customer asks whether credit-card cash back or reward points on one or more transactions are correct. It supports a precise calculation only where the applicable card's earn rate and eligibility are documented. Do not infer reward rates for cards or promotions not covered by the available policy.

## Safety, identity, and scope

1. Determine the customer record from the identifier they supply. A name lookup may locate a candidate record but is not, by itself, identity verification.
2. Before discussing account-specific transaction or reward details, confirm any two of the following four fields against the retrieved customer record: date of birth, email address, phone number, and street address. Ask the customer to provide the fields; do not recite them first.
3. Obtain the current time and call `log_verification` only after two fields match. Supply the complete retrieved record required by that tool and the current timestamp. If verification fails or is incomplete, do not reveal transaction details; ask for another verification field or offer general reward-policy information only.
4. Retrieve the verified customer's credit-card accounts and transaction history. Limit the review to completed transactions and the card(s) whose documented rules support a calculation. Do not expose unrelated account balances, contact information, or transactions.
5. Clarify the card or purchase the customer is concerned about when necessary. If no card is specified, state the scope of the review rather than claiming that every card was validated.

## Documented rules in this package

Read `references/reward_rules.md` before interpreting the data. The currently supported calculation is for **Crypto-Cash Back**: 2.0% on eligible purchases. Its stored reward value is points representing cash back, at 1 point = $0.01. The known eligible category list may be used to establish category support, but an `Other` or unknown category must be reported as not determinable rather than treated as eligible.

For any cash-back card, stored points are cash-back cents and the expected points are:

```
floor(transaction_amount_in_dollars * earn_rate_percent)
```

For example, the percentage numeral is `2.0` for a 2.0% earn rate. This expression is equivalent to flooring the cash reward in dollars multiplied by 100. Always truncate each purchase independently; never round to nearest or aggregate fractional points across purchases.

EcoCard uses true sustainability points and is outside the cash-back calculation unless its separate documented rate and category rule are available.

## Run the audit helper

Use `scripts/audit_rewards.py` to prevent decimal/rounding mistakes. It reads one JSON object from stdin and writes one JSON object to stdout.

Input schema:

- `transactions` (required): array of transaction objects with `transaction_id`, `credit_card_type`, `transaction_amount`, `category`, `status`, and `rewards_earned`.
- `card_type` (required): exact card type to audit.
- `earn_rate_percent` (required): numeric/string percentage numeral, such as `"2.0"`.
- `eligible_categories` (optional): list of categories documented as eligible. If omitted, the helper calculates all completed transactions on the specified card.
- `completed_status` (optional): status to include; defaults to `COMPLETED`.

For a documented Crypto-Cash Back review, supply its documented card type, a rate of `2.0`, and the known eligible categories from `references/reward_rules.md`. Do not put a customer ID, transaction ID, or an expected outcome into the Skill; obtain all transaction values at runtime.

Runnable invocation pattern:

```sh
python3 scripts/audit_rewards.py <<'JSON'
{"transactions": [...], "card_type": "<documented card type>", "earn_rate_percent": "<documented rate>", "eligible_categories": ["<documented category>"]}
JSON
```

The helper returns `audited`, `matches`, `mismatches`, `indeterminate`, and `skipped` arrays, plus summary counts. A mismatch contains the awarded and expected points, difference in points, and cash-value difference. An indeterminate record is deliberately not a mismatch: its category is not supported by the supplied category list. Invalid monetary/reward fields are skipped with a reason.

Validate the result before relying on it:

- Confirm `audited_count + indeterminate_count + skipped_count` equals the number of card-matched records in scope.
- Confirm each expected value is an integer and uses `floor(amount × rate_percent)`.
- Confirm that only `COMPLETED` transactions are audited.
- Confirm every mismatch has a nonzero `point_difference` and that `cash_difference` equals points times $0.01.

## Customer response and next step

Give a short, transaction-level explanation: date, merchant, amount, awarded points/cash value, expected points/cash value, rate, and truncation rule. Clearly distinguish an established discrepancy from a transaction whose rate or eligibility cannot be determined from the documented policy. Do not promise an adjustment or imply that a dispute is already filed.

When a supported mismatch exists and the customer wants to pursue it, provide the customer-initiated tool named `submit_cash_back_dispute_0589` through `give_discoverable_user_tool`. Supply the verified customer's user ID and the specific mismatch transaction ID as its arguments. The customer, not the agent, executes the dispute tool. Confirm that the transaction ID is the one the customer intends to dispute, and note that review may later request category or promotion context.

If all supported transactions match, state that result and the calculation scope. If a requested card's rate is not documented, explain that it cannot be independently recalculated from the available rules; do not manufacture a rate from historical transaction patterns.
