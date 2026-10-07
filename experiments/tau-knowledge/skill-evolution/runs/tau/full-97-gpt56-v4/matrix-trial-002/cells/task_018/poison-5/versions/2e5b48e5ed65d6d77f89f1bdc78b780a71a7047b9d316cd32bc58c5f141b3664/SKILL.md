---
name: cash-back-reward-discrepancy-review
description: Review completed credit-card transactions for documented reward-rate discrepancies, explain point-to-cash-back conversion and rounding, and route a verified customer to the required self-service cash-back dispute tool. Use when a customer says cash back or reward points appear incorrect, including when they cannot identify the affected transaction.
---

# Cash-Back Reward Discrepancy Review

## Scope and safety

Use this Skill to investigate; it does **not** change reward balances or submit a dispute on the customer's behalf. Follow the banking control below before accessing or acting on account information: verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

For this workflow:

1. Ask for an account locator (exact full name or email) if needed. Locate the customer using the corresponding user-information tool.
2. Before reviewing non-public account data or offering a dispute action, ask the customer to provide two of the following profile fields without first reciting them: date of birth, email, phone number, or address.
3. Compare the two customer-provided fields against the retrieved profile. If both match, obtain the current time and call `log_verification` with the complete retrieved profile and timestamp. If verification fails or is incomplete, do not disclose account data or proceed with the review.
4. Retrieve the verified customer's credit-card accounts and transaction history. Confirm the transaction belongs to that verified user and that its listed card type corresponds to one of their accounts. Review only completed transactions. No balance, payment, or credit availability check is needed for a read-only reward calculation, but complete those checks if the workflow later expands into a banking action.

Do not expose a full transaction history unnecessarily. Summarize only the relevant reviewed transactions after verification.

## Reward interpretation and calculation

- For cash-back cards, database `rewards_earned` values labelled “points” represent cash back at **1 point = $0.01**. Thus, a point difference is also a cash-back difference in cents.
- Compute each transaction separately, never on a statement total: `expected_points = floor(purchase_amount_in_dollars × applicable_points_per_dollar)`.
- Fractional points are always truncated down, not rounded to nearest.
- A card's documented rate applies only where its terms establish it. Do not infer a rate from a reward amount or assume a bonus rate from a merchant name.
- The documented Crypto-Cash Back rate is 2.0% (2 points per dollar) on eligible purchases. The supplied helper recognizes that documented rule and checks it only for recognized eligible categories. It does not manufacture terms for other cards.
- The EcoCard earns 5 points per dollar for Green/Sustainable purchases and 1 point per dollar for other eligible purchases. It is a true points card, although its points also redeem at $0.01 per point.
- If card-specific terms, eligibility, category treatment, or a promotion are not documented in the current task materials, mark the transaction **unassessable**, explain what is missing, and do not call it an error.

## Analysis helper

Use `scripts/review_rewards.py` for deterministic calculation once transactions have been represented as JSON. It reads one JSON object from stdin and emits one JSON object on stdout.

### Input schema

```json
{
  "transactions": [
    {
      "transaction_id": "string",
      "credit_card_type": "string",
      "transaction_amount": "decimal dollars",
      "category": "string",
      "status": "COMPLETED",
      "rewards_earned": "integer points"
    }
  ],
  "rules": {
    "Optional Card Type": {
      "default_points_per_dollar": "decimal",
      "category_points_per_dollar": {"Category": "decimal"},
      "eligible_categories": ["Category"]
    }
  }
}
```

`rules` is optional. It can supply current-task card terms for cards other than the built-in documented Crypto-Cash Back and EcoCard rules. A supplied rule for a card overrides the built-in rule. The helper reports malformed records and missing rate/eligibility information instead of guessing.

### Output schema

The output has `findings` (assessable completed transactions), `discrepancies` (findings where expected and recorded points differ), `matches`, `unassessable`, `skipped`, and `errors`. Each assessable finding includes the expected and recorded points, their dollar equivalents, the applied rate, and whether it matches. Validate that every discrepancy has a nonempty transaction ID, a verified-owner card type, numeric amounts, and a documented rate before discussing it with the customer.

A minimal runnable structural check is:

```sh
printf '{"transactions":[]}' | python3 scripts/review_rewards.py
```

## Customer outcome and dispute routing

1. Explain the calculation plainly, including truncation and the point-to-dollar conversion. Identify a discrepancy only when the documented per-transaction calculation differs from recorded points.
2. If no documented discrepancy is found, say so and invite the customer to provide a particular transaction, receipt, promotion, or category concern for further review. Do not claim that undocumented card terms were checked.
3. If a discrepancy is found, confirm the selected transaction ID, its card, merchant/date/amount, and the customer's intent to dispute that specific transaction. Confirm it belongs to the verified user.
4. The documented submission method is customer self-service. Use `give_discoverable_user_tool` to provide `submit_cash_back_dispute_0589` with JSON arguments containing the verified `user_id` and the one confirmed `transaction_id`. Tell the customer to execute that tool themselves. Do not call an agent-side equivalent and do not submit multiple transactions without individual confirmation.
5. State that category or promotion context may be requested during review. Do not promise an adjustment, calculate an unsupported adjustment, or reveal sensitive card details.

If tool access is unavailable, provide the exact documented tool name and required identifiers rather than claiming a dispute was submitted. Escalate only if a required review cannot be completed through the documented process or the customer requests a human after the available self-service route is explained.
