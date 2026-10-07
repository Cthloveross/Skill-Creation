---
name: credit-card-rewards-audit
version: 1.0.0
description: Audit posted rewards for a Silver Rewards Card and Business Silver Rewards Card using transaction records, merchant categories, exclusions, account-opening dates, and the documented Business Silver promotional period. Use when a customer believes cash-back rewards were calculated incorrectly.
---

# Credit-card rewards audit

Use this Skill to investigate a rewards concern without making unsupported account changes. It distinguishes the personal Silver Rewards Card from the Business Silver Rewards Card, evaluates each completed transaction, and explains database reward points as cash back.

## Required facts

Obtain or use the runtime-provided records for the customer, including:

- card type and account-open date for each relevant account;
- transaction ID, card type, merchant, amount, transaction date, category, posting status, and rewards earned;
- the current date only when it is relevant to explaining a promotion.

If account-specific records have not already been authorized for discussion, first follow the runtime's identity-verification procedure. The supplied `log_verification` tool requires confirmation of two of date of birth, email, phone number, and address, plus a current timestamp. Do not treat a name alone as two-factor verification. Do not log verification until those fields have actually been confirmed by the customer.

Do not expose unrelated accounts, personal profile fields, or transactions. Never make an adjustment, redemption, or account change merely because the audit finds a discrepancy.

## Policy encoded by this Skill

- Rewards stored as points on both cards are cash back at **1 point = $0.01**.
- **Silver Rewards Card:** eligible Travel and Software transactions earn 4%; all other purchases earn 1%.
- **Business Silver Rewards Card:** eligible Travel and Software transactions earn 10%; other purchases earn 1%.
- On the Business card, Concur, SAP Concur, Expensify, Navan, Apple, Microsoft, Dell, Xbox Game Pass, PlayStation Plus, Nintendo Switch Online, Coursera, Udemy, LinkedIn Learning, Skillshare, and Pluralsight receive the 1% standard rate even if a supplied category says Travel or Software.
- A Business-card customer whose account opened on or after 2024-11-14 and on or before 2025-11-14 earns double the normal applicable rate during the first six calendar months beginning on their account-open date. The first date after that six-month anniversary is not promotional. The promotion doubles standard-rate purchases too.
- Assess only `COMPLETED`/posted transactions. Pending, reversed, refunded, or unknown-status transactions need a separate status review and must not be asserted as a rewards error.
- Category information is the available evidence of merchant coding. If no reliable category or merchant coding is provided, report that eligibility cannot be confirmed rather than assuming a bonus rate.

Rewards are expected in whole points. Use ordinary half-up rounding of amount × rate × 100, matching the points representation.

## Procedure

1. Confirm which card(s) the customer wants reviewed. Retrieve accounts and transactions only for the confirmed customer through the normal banking tools. Keep the two card types separate even if transaction records are returned together.
2. Normalize the retrieved records into the JSON input described below and run:

   ```
   python3 scripts/audit_rewards.py < audit_input.json
   ```

   The script reads JSON from standard input and writes one JSON report to standard output. It uses only input supplied at runtime; do not add current customer IDs, transaction IDs, or precomputed conclusions to the package.
3. Review each `review_items` entry. A nonzero `delta_points` means `awarded - expected`: a negative number is a shortfall and a positive number is more than the documented expected amount. Check the category, merchant exclusion flag, date, and rate explanation before characterizing it to the customer.
4. Summarize results by card in clear cash-back terms. Include transaction date, merchant, purchase amount, expected and awarded rewards in points and dollars, and the difference for every discrepancy. Explain that points are cash back at one cent each. Also identify transactions that correctly received the standard rate because of an exclusion, non-bonus category, or after-promotion date.
5. Be precise about uncertainty: merchant categories determine bonus eligibility, and a category may be reviewed with documentation if it appears wrong. Do not say a transaction is definitely misclassified if the supplied category supports its rate.
6. If an internal, documented rewards-correction workflow/tool is available in the live environment, use it only after applicable verification and only for confirmed shortfalls. This Skill does not invent or unlock such a tool. If no documented correction mechanism is available, explain the findings and offer the supported review/escalation path; transfer only when the customer requests a human or the runtime policy requires it.

## Input schema for `scripts/audit_rewards.py`

```json
{
  "accounts": [
    {"card_type": "Silver Rewards Card", "date_of_account_open": "YYYY-MM-DD"},
    {"card_type": "Business Silver Rewards Card", "date_of_account_open": "YYYY-MM-DD"}
  ],
  "transactions": [
    {
      "transaction_id": "string",
      "credit_card_type": "Silver Rewards Card or Business Silver Rewards Card",
      "merchant_name": "string",
      "transaction_amount": "decimal number or string",
      "transaction_date": "YYYY-MM-DD",
      "category": "Travel, Software, or another category",
      "status": "COMPLETED",
      "rewards_earned": "integer points"
    }
  ]
}
```

The output contains `cards`, one item per requested supported card, with totals and per-transaction results. `review_items` contains only completed entries whose expected and awarded points differ. `unreviewed` records unsupported card types, missing dates/amounts, malformed records, and non-completed transactions with a reason. Validate that all requested supported-card transactions appear exactly once in either a card's `transactions` list or `unreviewed`, and that each review item has a nonzero delta.
