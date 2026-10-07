---
name: cash-back-rewards-review
description: Review posted credit-card cash-back earnings when a customer believes transaction rewards are wrong. Use for card reward-rate comparisons, merchant-category eligibility checks, and explaining items that cannot be verified because the applicable rate is unavailable.
---

# Cash-Back Rewards Review

Review rewards only after identity, authority, ownership, and transaction status are established. This Skill calculates documented rates; it does not independently post rewards adjustments, alter points, or assume an unstated default rate.

## Required inputs

Obtain at runtime:

- The customer's identity information and successful two-field verification.
- The verified customer's credit-card account(s) and the relevant card type.
- That customer's transaction history, including amount, merchant, category, status, date, and recorded `rewards_earned` points.
- The card's documented rate rules. Do not infer a default rate from a small reward amount.

For cash-back cards, database `rewards_earned` points represent cash back at **1 point = $0.01**. A documented cash-back percentage can therefore be compared to expected points as `purchase amount × rate × 100`.

## Safe banking workflow

1. **Identify and verify the customer before disclosing account-specific results or taking any account action.** Ask the customer to confirm any two of date of birth, email, phone number, and address. Look up the customer with the provided identifier, compare both fields to the returned record, obtain the current time, then call `log_verification` with all returned identity fields and that timestamp. Do not treat a name alone as verification.
2. Retrieve credit-card accounts for the verified `user_id`. Confirm the requested card belongs to that user, its card type matches the review, and the customer has authority over it. Retrieve transactions using the same verified `user_id`; review only records whose card type matches the owned card.
3. Confirm each item is posted/completed rather than merely authorized or pending. Exclude/referral-handle returned or refunded purchases because rewards reverse when credits post. Keep transaction ID, date, merchant, amount, category, status, and earned points in the review record.
4. Establish eligibility from supplied card terms and the recorded merchant category, not solely the merchant name. For a Silver Rewards Card, the documented 4.0% rate applies to eligible **Travel** and **Software** transactions. Travel eligibility depends on how the merchant submitted the category; direct airlines and hotels are typical examples, while processor-masked or differently coded purchases may not qualify.
5. Do **not** claim a rate for Shopping, Dining, or any other non-bonus category unless a reliable card term supplies it. They are valid rewards categories, but their Silver Rewards Card default rate is not provided by the supplied documentation. Mark those transactions `rate_unavailable` rather than estimating a shortfall.
6. Normalize the applicable rate rules and transaction records into the JSON schema below and run `scripts/review_rewards.py`. Inspect the per-transaction status and totals. A lower earned-points value than the documented expected value is a potential shortfall; equal or higher values are not a shortfall under that documented rule.
7. Clearly tell the customer which posted transactions were confirmed, which need a category/rate review, and why. State points and dollar equivalents where useful. Ask for receipts only when merchant categorization needs support. If the customer cannot provide terms for categories with unavailable rates, explicitly say a full numerical review of those categories cannot be completed from available information; offer a customer-service/category review rather than inventing a rate.
8. There is no declared reward-adjustment action in this runtime. Do not modify reward balances or promise an adjustment. If an adjustment or deeper investigation is needed, use the organization’s supported escalation process; if a human transfer is requested or necessary, use `transfer_to_human_agents` with an accurate summary and the applicable reason.

### Required control checklist

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this read-only rewards review, identity, authority, owned card/card type, transaction-card match, posted status, reward eligibility, and rate availability are the applicable prerequisites. Available balance, fees, limits, cutoff, recipient, and confirmation prerequisites become mandatory if the request changes into a redemption, payment, transfer, adjustment, or other account action.

## Calculator interface

`scripts/review_rewards.py` reads one JSON object from standard input and emits one JSON object on standard output.

Input schema:

```json
{
  "rate_rules": {"Travel": "4.0", "Software": "4.0"},
  "transactions": [
    {
      "transaction_id": "string",
      "merchant_name": "string",
      "transaction_amount": "0.00",
      "category": "Travel",
      "status": "COMPLETED",
      "rewards_earned": 0
    }
  ]
}
```

`rate_rules` values are percentages, not fractions. Only supply rules supported by card terms. `transaction_amount` may be a number or decimal string. The script uses decimal arithmetic and rounds expected points to the nearest whole point using half-up rounding. Its output includes each normalized transaction, its expected points/cash-back amount when calculable, a status, and aggregate totals.

Runnable example (replace the JSON with actual runtime records):

```sh
python3 scripts/review_rewards.py <<'JSON'
{"rate_rules":{"Travel":"4.0","Software":"4.0"},"transactions":[]}
JSON
```

Validate before communicating results: output must parse as JSON, each input transaction must appear once, known-rate completed entries must have `expected_points`, and entries without an applicable rule must be `rate_unavailable`. Treat `invalid_input` output as a data-quality issue to correct from the bank records, not as a reward finding.

## Customer-response template

Use a concise, evidence-based response: identify the reviewed card and completed transactions, say that one point equals one cent for this cash-back card, provide the documented-rate result for each eligible category, and distinguish unavailable-rate items from discrepancies. Never state that a merchant "should" receive a bonus based only on its name; recorded category and merchant coding control eligibility.
