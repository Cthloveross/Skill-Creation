---
name: credit-card-rewards-discrepancy-audit
description: Audit posted cash-back rewards on Silver Rewards Card and Business Silver Rewards Card transactions, identify under- and over-credit discrepancies under documented rates and promotions, and prepare an evidence-based rewards-servicing escalation. Use after verifying a cardholder who asks to review incorrect cash back or stored reward points.
---

# Credit Card Rewards Discrepancy Audit

Use this Skill for a read-only transaction-level cash-back audit. It does not redeem points, change rewards, debit points, reverse a credit, or apply an adjustment.

> Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Prerequisites and safe handling

1. Treat a supplied name, email, user ID, or account name as a lookup lead only, not identity verification.
2. Before retrieving or disclosing account-specific card or transaction information, verify customer control of the account. Ask the customer to confirm at least two of date of birth, email, phone number, and address against the customer record. Obtain the current timestamp and call `log_verification` with the complete record only after two fields match.
3. Confirm the verified customer owns every account to be reviewed and that the request concerns their own rewards. Do not disclose another account holder's transactions, balances, or rewards.
4. Retrieve the customer's credit-card accounts and transaction history with the normal read-only banking tools. Retain account opening date, card type, transaction date, merchant, amount, posted category, status, and rewards earned.
5. Do not use the current aggregate reward-points balance to reconcile a transaction list; redemptions, reversals, earlier activity, and unlisted activity may affect that balance.

## Program rules used by the audit

- Database `points` on both named cards represent cash back: **1 point = $0.01**.
- **Silver Rewards Card:** posted Travel or Software/SaaS transactions earn 4.0%; other purchases earn 1.0%.
- **Business Silver Rewards Card:** posted Travel or Software/SaaS transactions earn 10.0%; other purchases earn 1.0%.
- The Business Silver double-cash-back offer requires an account opening date from 2024-11-14 through 2025-11-14, inclusive. During the first six calendar months after opening, it doubles the applicable base rate: 20.0% for qualifying Travel/Software and 2.0% for other spending. No enrollment is required.
- Eligibility is determined by the posted merchant category. Do not claim that a merchant should have a different category without a category review and supporting documentation.
- Business Silver named exclusions use the ordinary 1.0% rate even when categorized as Travel or Software: Concur, SAP Concur, Expensify, Navan, Apple, Microsoft, Dell, Xbox Game Pass, PlayStation Plus, Nintendo Switch Online, Coursera, Udemy, LinkedIn Learning, Skillshare, and Pluralsight. An otherwise applicable promotion doubles that ordinary rate to 2.0%.
- Evaluate only positive posted or completed purchases. Pending, returned, refunded, reversed, negative, missing-category, ambiguous-account, invalid-date, and unsupported-card records require review rather than a rate conclusion.

## Run the calculation

Use `scripts/audit_rewards.py` through `run_skill_script`. The script accepts one JSON object on stdin and emits one JSON object on stdout. It makes no network calls and cannot perform a banking action.

### Input schema

```json
{
  "accounts": [
    {
      "account_id": "optional account identifier",
      "card_type": "Silver Rewards Card or Business Silver Rewards Card",
      "date_of_account_open": "YYYY-MM-DD or MM/DD/YYYY"
    }
  ],
  "transactions": [
    {
      "transaction_id": "optional identifier",
      "account_id": "optional; required if card type matches multiple supplied accounts",
      "credit_card_type": "required if account_id is omitted",
      "merchant_name": "merchant descriptor",
      "transaction_amount": "$0.00 or numeric amount",
      "transaction_date": "YYYY-MM-DD or MM/DD/YYYY",
      "category": "posted merchant category",
      "status": "COMPLETED or POSTED",
      "rewards_earned": "integer points or a value such as '123 points'"
    }
  ],
  "promo_end_inclusive": false
}
```

The helper accepts the `MM/DD/YYYY` dates commonly returned by transaction-history tools as well as ISO dates. Preserve and convert the source date to a readable calendar date in the customer response.

`promo_end_inclusive` defaults to `false`, so the six-calendar-month anniversary is outside the initial six-month period. Set it to `true` only if an applicable servicing policy explicitly defines that anniversary as included, and record that policy basis.

Example call shape (replace all placeholders with verified customer records):

```json
{
  "relative_path": "scripts/audit_rewards.py",
  "input_json": {
    "accounts": [{"account_id": "...", "card_type": "Business Silver Rewards Card", "date_of_account_open": "MM/DD/YYYY"}],
    "transactions": [{"account_id": "...", "merchant_name": "...", "transaction_amount": "$0.00", "transaction_date": "MM/DD/YYYY", "category": "Travel", "status": "COMPLETED", "rewards_earned": "0 points"}]
  }
}
```

### Output interpretation and validation

The output contains one `results` row for each supplied transaction and a `summary`.

- `match`: recorded points equal rounded expected points.
- `under_earned`: `shortfall_points` and `shortfall_cash_back` are positive. This is a candidate for rewards-servicing review, not a completed adjustment.
- `over_earned`: `excess_points` and `excess_cash_back` are positive. This is a transparent variance report only; it never authorizes a debit, reversal, accusation, or customer action.
- `not_evaluated`: `reason` states why a policy conclusion cannot safely be made.

Validate before communicating: result count equals input count; every evaluated row has a nonnegative integer expected-point value, stated rate, and calculation basis; every under-earned row has nonnegative shortfall fields; every over-earned row has nonnegative excess fields; and summary totals equal the sums of the corresponding rows. Resolve invalid input, account ambiguity, or unsupported records before claiming a determination.

## Customer response and escalation

Explain the reviewed period and cards, relevant rates, and that stored points are cash back. Include this exact standalone conversion statement in every customer-facing result that discusses points or cash values: **`1 point = $0.01`**.

Report **every evaluated discrepancy**, not only shortages. For each `under_earned` or `over_earned` row, clearly label the direction and list:

- merchant and readable transaction date;
- purchase amount;
- posted category and applicable rate;
- recorded points and expected points;
- the point variance and dollar value; and
- the calculation basis.

Keep totals distinct: aggregate only `under_earned` shortfalls when describing potentially missing cash back. Do not net an over-credit against shortages. State that an over-credit is included for transparency and will be reviewed by rewards servicing; do not say it has been debited, reversed, recovered, or adjusted.

Separate confirmed policy arithmetic from records needing posting or category review. Invite receipts or invoices when category coding may be wrong.

When any confirmed shortfall, over-credit, or unresolved category issue needs servicing, provide the specialist with the completed verification status and the merchant, date, amount, category, recorded points, expected points, variance, applicable rate, calculation basis, and any documentation. If the available human-transfer path is needed, transfer with `transfer_to_human_agents` using reason `complex_billing_dispute`. Tell the customer this is a **rewards review, not a charge dispute**, and state exactly: **“No points adjustment has been made yet.”** A rewards servicing specialist will determine eligibility and complete any available servicing action. If no discrepancy is found, explain the applicable rate and offer to review another posted transaction.
