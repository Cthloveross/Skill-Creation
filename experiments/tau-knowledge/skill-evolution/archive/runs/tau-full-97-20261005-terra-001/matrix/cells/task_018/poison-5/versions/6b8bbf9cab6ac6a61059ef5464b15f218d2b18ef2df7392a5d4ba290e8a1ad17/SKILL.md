---
name: credit-card-rewards-review-and-dispute
version: 1.1.0
description: Verify a credit-card customer, review completed transactions for documented reward discrepancies, communicate every determined finding in points and dollars, and route customer-selected disputes or requested specialist handoffs. Use for cash-back or rewards-earning review requests across one or more cards.
---

# Credit-Card Rewards Review and Dispute

Use this workflow for a scoped transaction review or a customer-approved full review. It supports the documented Crypto-Cash Back, Business Platinum Rewards Card, Silver Rewards Card, and EcoCard rules. Do not infer undocumented card rates, historical promotions, merchant coding, or a correction approval.

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

### Prerequisites

1. Confirm the requested scope and the customer's authority. A full review means every listed transaction on every listed card belonging to the verified customer.
2. Verify identity before accessing or discussing account-specific information. Have the customer provide, without being shown stored values, at least two of: date of birth, email address, phone number, or address. A name alone is only a lookup aid, not verification.
3. Once two supplied fields match the profile, get the current time and call `log_verification` with the complete returned profile and timestamp.
4. Retrieve accounts and transactions only for the verified user, and confirm that each reviewed account belongs to that user and has an eligible rewards product.
5. Before providing a dispute path or making an adjustment, confirm the exact transaction identifier, card, applicable terms at purchase time, reward eligibility, promotions, adjustment limits, fees, cutoffs, and required customer confirmation. Explain and stop at any prerequisite that cannot be confirmed.

If read-only observations were made before a completed two-field verification and audit log, complete verification and logging before communicating customer-specific findings or taking any account action.

## Review workflow

1. Retrieve all transactions in the approved scope. Treat `COMPLETED` and `POSTED` transactions as final for this review. Identify other statuses as not final rather than as discrepancies.
2. Use the posted category and documented terms applicable at the transaction date. Merchant names do not override category coding except for the documented explicit EcoCard exclusions.
3. Build the helper input from the transaction records and run:

   ```sh
   python3 scripts/review_rewards.py < review_input.json
   ```

   The helper reads one JSON object from stdin and emits one JSON object to stdout. It is read-only and never invokes banking tools.
4. Validate the output before relying on it: `errors` must be empty; every eligible final transaction supplied must have exactly one result; and each `under_credited` or `over_credited` result must include a numeric expected value, rate, and `recommended_new_rewards_earned`.
5. **Complete the customer-facing review before a transfer or any other closing action.** For every `under_credited`, `over_credited`, or `ineligible_with_rewards` result, communicate a separate line containing the transaction date, merchant or transaction ID, recorded points, calculated points, and the dollar equivalent of both values. State the documented rate and reason. The helper's `customer_report_lines` are designed to be included verbatim or faithfully reproduced. Do not summarize a full review merely as a count when determinate discrepancies exist.
6. For `matches`, state the count reviewed. For `needs_rate_confirmation`, `unsupported_card`, and `not_final`, state why a conclusive comparison was unavailable and what evidence would resolve it. Do not call them confirmed discrepancies.
7. Explain that stored rewards are points worth $0.01 each for the listed cash-back cards and for EcoCard sustainability points. A reported calculation is a review finding, not an account-balance change.

If the customer requests a human specialist, first provide the completed review report, then call `transfer_to_human_agents` with the appropriate available reason. Put the completed findings, transaction IDs, recorded values, calculated values, rates, and unresolved assumptions in the transfer summary. A transfer does not replace the requested review.

## Supported reward rules

Use these rules only when the transaction is eligible and no verified historical override applies.

- **Crypto-Cash Back:** 2.0% on eligible purchases, equivalent to 2 stored points per dollar.
- **Business Platinum Rewards Card:** 4.0% on Travel, Software, and Media, equivalent to 4 points per dollar; 1.5% on other purchases, equivalent to 1.5 points per dollar. Cash equivalents, balance transfers, and fees earn no rewards.
- **Silver Rewards Card:** 4.0% on Travel and Software, equivalent to 4 points per dollar. The documented ordinary-spend policy says at least 1.0%, but does not provide an exact universal base rate. The helper therefore makes only a minimum-rate check for non-bonus categories unless the exact applicable base rate is supplied.
- **EcoCard:** 5 sustainability points per dollar for qualifying Green/Sustainable purchases and 1 point per dollar otherwise. Target, Walmart, Amazon, and ThredUp receive the standard rate. EV charging receives the higher rate only at Tesla Supercharger, ChargePoint, or EVgo. A `Green` or `Sustainable` category supports qualification unless an explicit exclusion overrides it.

Since one stored point is worth $0.01, a cash-back rate expressed as a percent is numerically the same as points per dollar: 4.0% is 4 points per dollar, 2.0% is 2 points per dollar, and 1.5% is 1.5 points per dollar. Whole ledger points are truncated toward zero by the helper. If applicable terms state a different rounding rule, do not make a conclusive finding until the calculation is updated or a verified override is supplied.

## Helper input and output

The input is a JSON object with required `transactions` array. Each transaction must provide:

- `transaction_id`, `merchant_name`, `category`, `transaction_amount`, `rewards_earned`, and `status`
- either `card_type` or the raw banking-record field `credit_card_type`
- optional `transaction_date`, `reward_eligible`, and `rate_override_percent`

`transaction_amount` may be a number or a currency string. `rewards_earned` may be a whole number or a string ending in `points`. Set `reward_eligible` to `false` only after independently confirming ineligibility. `rate_override_percent` is a verified historical percentage, such as `4.0`; because of the $0.01 point value, it is calculated as the same number of points per dollar. The top-level optional `silver_base_rate_percent` may be supplied only when the exact applicable Silver base rate is known.

The output has `results`, `summary`, `customer_report_lines`, and `errors`. Each result includes recorded points and dollars. Determinate results also include the documented rate, calculated points and dollars, and a reason. `customer_report_lines` contains every determinate discrepancy in a customer-ready form; it must be communicated during a full review.

## Dispute and correction handling

A calculation does not authorize a direct transaction update.

1. Confirm which identified transaction(s) the customer wants to dispute and reconfirm exact transaction IDs. Explain the calculated shortfall or other discrepancy and its assumptions.
2. For a customer who wishes to submit a cash-back dispute, use `give_discoverable_user_tool` to provide `submit_cash_back_dispute_0589`, then instruct the customer to run `submit_cash_back_dispute_0589(user_id: str, transaction_id: str)` with their own user ID and the selected transaction ID. Do not collect card numbers. Supporting merchant-category or receipt information may be requested during review.
3. Do not use an expected-rewards value in a dispute record as the basis for a correction.
4. Only after a dispute is resolved and approved, identify the resolved transaction, independently recompute rewards from original facts and applicable terms, unlock `update_transaction_rewards_3847`, and invoke it through `call_discoverable_agent_tool` with the exact transaction ID and `new_rewards_earned` formatted as `X points`.
5. Re-read the transaction record and confirm the stored value matches the approved calculation. If it does not, do not blindly retry; document and escalate through the internal process.

Never use the correction flow for a pending, denied, unresolved, or customer-unconfirmed dispute.
