---
name: credit-card-reward-discrepancy-review
description: Review posted credit-card transactions for possible reward under-earnings using documented card rules, clearly separate supported findings from unknown policy coverage, and route customer disputes or approved internal corrections through the prescribed tools.
---

# Credit-Card Reward Discrepancy Review

Use this Skill when a verified customer asks to investigate possibly incorrect credit-card cash back or rewards. It supports these documented programs:

- **Crypto-Cash Back:** 2.0% on eligible purchases.
- **Business Platinum Rewards Card:** 4.0% on travel, software, and media; 1.5% on other purchases. Cash equivalents, balance transfers, and fees do not earn rewards.
- **Silver Rewards Card:** 4.0% on posted travel and software purchases. Do not calculate a rate for other categories unless a separate authoritative policy is supplied.
- **EcoCard:** 5 points per dollar on qualifying green purchases and 1 point per dollar otherwise. Target, Walmart, Amazon, and ThredUp are standard-rate exclusions. EV charging earns the green rate only at Tesla Supercharger, ChargePoint, or EVgo.

Transaction reward values represented as `points` are redeemable at $0.01 per point. This also applies to cash-back cards; EcoCard remains a points program but has the same redemption value.

## Banking controls and prerequisites

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

Treat access to a customer's transaction history, a rewards dispute, and any rewards adjustment as banking work. Before retrieving or discussing nonpublic transaction details:

1. Confirm the requester is the customer or an authorized representative and verify two of four identity fields: date of birth, email, phone number, and address.
2. Retrieve the customer record only after the customer supplies an allowed lookup detail. Match the two fields against the record, obtain the current time, and call `log_verification` with all fields and the timestamp.
3. Retrieve card accounts for the verified user. Match each reviewed transaction's `user_id` and card type to that user's account. Do not review another user's transactions or an account whose ownership is not established.
4. Record applicability of the remaining prerequisites. For a read-only reward review, available balance/credit, transfer cutoffs, recipients, and payment fees are normally not operative; card-product eligibility and transaction status are operative. For crypto redemption questions, separately disclose the documented 1.25% conversion fee and $30 minimum; do not confuse either with the purchase earn rate.
5. Check that the transaction is posted or completed, is not a return or credit, and has a usable net purchase amount. Reward amounts are based on net purchases after returns and credits.
6. A customer may submit a dispute themselves; no agent-side adjustment is authorized merely because an analysis identifies a possible discrepancy. An internal update additionally requires a resolved, approved dispute and the applicable internal authorization/confirmation record.

If identity, authority, ownership, transaction status, or required information cannot be confirmed, do not expose transaction results or submit/update anything. Explain what is missing or transfer through the normal support process when appropriate.

## Review workflow

1. After verification, use `get_credit_card_accounts_by_user` and `get_credit_card_transactions_by_user` for the verified user.
2. Determine review scope from the customer's request and available policy. If a rate is not documented, label those rows **not reviewable** rather than inferring a base rate. In particular, only evaluate Silver Rewards Card travel and software rows unless authoritative additional Silver terms are provided.
3. Convert the returned transaction records into the JSON input described below and run the analyzer. The default whole-point method is truncation (`floor`); retain this stated calculation assumption in the case notes because the supplied policy does not state a fractional-point rounding rule.
4. Check each `under_earned` result against the original transaction data: card type, merchant, category, completed/posted state, amount, exclusions, and any merchant-classification information. A category on a transaction is evidence of how it posted, not proof that an unverified merchant should receive a bonus rate.
5. Tell the customer which supported transactions appear under-earned, including merchant, date, amount, recorded points, expected points, and point difference. State that 100 points equal $1.00. Do not present `not_reviewable`, `unresolved`, or unsupported rows as confirmed errors.
6. For a possible under-earning the customer wants reviewed, follow the prescribed customer-initiated dispute process below. Do not submit disputes automatically and do not use sensitive card details.

### Script interface

Run:

```sh
python3 scripts/review_rewards.py < review-input.json
```

The script reads one JSON object from standard input and emits one JSON object to standard output. It has no external dependencies and does not call banking tools.

Input schema:

```json
{
  "transactions": [
    {
      "transaction_id": "string",
      "credit_card_type": "string",
      "merchant_name": "string",
      "transaction_amount": "USD amount",
      "transaction_date": "optional date",
      "category": "optional category",
      "status": "COMPLETED or POSTED",
      "rewards_earned": "whole points",
      "is_return_or_credit": false,
      "is_ev_charging": false,
      "green_eligible": true,
      "merchant_of_record_confirmed": true
    }
  ],
  "scope": {
    "include_card_types": ["optional card-type names"],
    "whole_point_rounding": "floor"
  }
}
```

`transactions` is required. Fields not needed for a specific rule may be omitted. Boolean eligibility fields are optional: provide them when case evidence establishes them. `transaction_amount` may be a JSON number or a dollar-formatted string. Supported rounding options are `floor` (default) and `half_up`.

Each finding includes a disposition, rate, expected whole points where determinable, actual points, point difference, cash-value equivalent, and reasons. Key dispositions are:

- `under_earned`: a supported calculated amount exceeds recorded points.
- `matches` or `over_earned`: the comparison is mathematically determinable; an over-earning is not a basis for a cash-back underpayment dispute.
- `not_reviewable`: the row is pending, returned, an explicit no-reward transaction, outside the authorized scope, or has no documented rate.
- `unresolved`: supplied merchant/category facts do not establish bonus eligibility.
- `invalid`: required input is malformed.

Validation before using results: ensure every intended posted transaction appears once, no output `invalid` row is treated as a finding, expected points are integers, and all customer-facing candidates have disposition `under_earned`. Reconcile script counts with the input records and preserve the returned assumptions and reasons in the review notes.

## Rule interpretation and edge cases

- Do not award a bonus based on merchant name alone when a posted category says otherwise. For Business Platinum and Silver, the posted travel/software/media category governs the documented bonus.
- Business Platinum standard-rate rows use 1.5 points per dollar; bonus rows use 4 points per dollar. Explicit cash-equivalent, balance-transfer, and fee rows expect zero rewards.
- Silver rows outside travel and software remain outside this Skill's supported calculation coverage. Gift cards, person-to-person payments, fees, interest, insurance premiums, returns, and refunds do not receive its 4% bonus.
- For EcoCard, explicit green eligibility or a Green/Sustainable category supports the 5-points-per-dollar rate, except the stated retailers and nonpartner EV charging. If a marketplace/payment processor is known not to be the qualifying merchant of record, or facts conflict, return `unresolved` instead of assuming a green bonus. Non-green purchases use 1 point per dollar.
- The analyzer cannot validate promotions, merchant category corrections, item-level green evidence, a return linked to an earlier purchase, or an unknown card's rate. Escalate those facts through a dispute/review rather than fabricating a calculation.

## Customer-initiated disputes

For each supported `under_earned` transaction the customer chooses to challenge, confirm the exact transaction ID and then provide the customer the documented tool:

`submit_cash_back_dispute_0589(user_id: str, transaction_id: str)`

Use `give_discoverable_user_tool` with discoverable tool name `submit_cash_back_dispute_0589` and arguments containing the verified customer's own `user_id` and the exact chosen `transaction_id`. Make clear that the customer executes the tool. Supporting receipts, merchant-category context, and promotion expectations may be requested during review. Do not create a dispute for a row merely because it is ambiguous, and do not claim that a dispute is approved.

## Approved internal corrections only

Only after a cash-back dispute is resolved and approved:

1. Locate the resolved dispute record and identify the affected transaction IDs. Do not use an `expected_rewards` value from the dispute as the calculation source.
2. Re-verify the prerequisites above, including ownership, the exact transaction/card, product eligibility, status, and approval/confirmation authority.
3. Recalculate using the applicable card policy and documented facts. Use the script for supported programs, retaining calculation notes; seek policy support for unsupported rates or promotions.
4. Unlock `update_transaction_rewards_3847` with `unlock_discoverable_agent_tool`.
5. Invoke it through `call_discoverable_agent_tool` with the exact `transaction_id` and `new_rewards_earned` formatted exactly as `"X points"`, where `X` is the validated whole-number total reward value, not a delta.
6. Retrieve the transaction history again and confirm the updated value. Retain the independent calculation and confirmation in the internal case record.

If resolved-dispute records, approval, the internal tool, or read-back confirmation are unavailable, do not make an update. Escalate through the authorized internal process instead.
