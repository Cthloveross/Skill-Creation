---
name: credit-card-rewards-investigation
description: Investigate apparent cash-back or rewards-point discrepancies on Silver Rewards Card and Business Silver Rewards Card transactions. Use after identity verification to compare posted transaction rewards with documented category rates, exclusions, and the Business Silver promotional period; explain findings and handle review or redemption questions safely.
---

# Credit Card Rewards Investigation

Use this Skill when a cardholder reports that cash back or rewards points appear incorrect, or asks why a travel/software purchase earned a particular amount. It supports analysis only; it does not alter rewards, redeem points, or create a dispute automatically.

## Safety and verification

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

1. Do not disclose card balances, points balances, transactions, or account-specific analysis based only on a name or email address.
2. Obtain the customer identifier needed to locate the profile, then have the customer confirm **two of four** profile fields: date of birth, email, phone number, and address. Compare both confirmations against the profile.
3. After two fields match, obtain the current timestamp and call `log_verification` with the complete profile values and timestamp. The logged verification establishes identity for the current interaction.
4. Confirm the customer owns the relevant card account before discussing its transactions. If card ownership is unclear, do not disclose or act on account data.
5. Read-only investigation needs no redemption or adjustment confirmation. Any later redemption, account credit, correction, or dispute requires the applicable product eligibility, balance/points, recipient/account, fees, limits, timing, and explicit confirmation checks before an action. Never infer authorization from an investigation request.

## Investigation workflow

1. Ask what looks incorrect and the approximate purchase dates or merchants, if the customer can provide them. Verify identity as above before account-specific discussion.
2. Retrieve the customer's credit-card accounts and transaction history. Match transactions to the relevant card type; if more than one account has the same card type and transactions lack an account ID, explain that account-level attribution cannot be established from the supplied records.
3. Analyze completed/posted transactions with `scripts/analyze_rewards.py`. Supply normalized account and transaction objects from tool results. The script is deterministic and does not call banking tools or make changes.
4. Review every discrepancy returned by the script. Report the transaction date, merchant, coded category, amount, expected and recorded points, and difference. State assumptions clearly: category-based eligibility is based on the transaction's supplied merchant category, and the analysis cannot independently prove merchant coding or detect off-ledger reversals/redemptions.
5. Explain that, on the cash-back cards covered here, database “points” are cash back: **1 point = $0.01** for a statement credit or Rho-Bank checking-account credit. Do not reconcile a displayed account points balance by summing transactions unless complete redemption, adjustment, reversal, and billing-cycle data is also available.
6. If the records show an apparent under-credit, explain the documented expected amount and offer a rewards/category review. Do not claim that a correction has been submitted or promise a result. If a supported case-creation/correction tool is not available and the customer wants escalation, transfer with the applicable `complex_billing_dispute` reason and a concise, verified summary. If the customer only wanted an explanation, provide it without transferring.
7. If records agree with the documented rules, explain the relevant rate, exclusion, promo timing, or merchant-category condition. Invite the customer to provide a receipt if they believe the merchant category itself is wrong.

## Rate rules used by the analyzer

### Business Silver Rewards Card

- Eligible transactions coded as `Travel` or `Software` earn 10.0% cash back; all other purchases earn 1.0%.
- The 10.0% rate depends on the merchant's category coding. Eligible travel includes airlines, lodging, car rentals, rideshare/taxi/limousine, passenger rail/bus/ferry, qualifying parking/tolls, travel agencies, and travel-coded online travel platforms.
- The following merchants are excluded from the 10.0% category bonus and receive the 1.0% standard rate: Concur, SAP Concur, Expensify, Navan, Apple, Microsoft, Dell, Xbox Game Pass, PlayStation Plus, Nintendo Switch Online, Coursera, Udemy, LinkedIn Learning, Skillshare, and Pluralsight. A merchant name containing one of these names is treated as excluded by the helper.
- A qualifying new customer whose account was opened during 2024-11-14 through 2025-11-14 receives double the otherwise applicable rate for the first six calendar months after account opening. Thus, bonus-category purchases earn 20.0% and standard-rate purchases earn 2.0% during that window. The helper treats the end as exclusive: a transaction on or after the date six calendar months after opening is outside the six-month window. Do not apply the promotion if the account opening date or transaction date is unavailable.
- Rewards are credited at the end of the billing cycle. For a completed transaction, calculate expected points from the purchase amount and rate, rounding fractional points to the nearest whole point with half-up rounding.

### Silver Rewards Card

- Eligible transactions coded as `Travel` or `Software` earn 4.0% cash back; all other purchases earn 1.0%.
- Eligibility depends on merchant category coding. Gift cards, person-to-person payments, bank fees, interest, insurance premiums, and returned/refunded purchases do not receive the enhanced rate; rewards on returns/refunds are reversed when the credit posts.
- Do not apply the Business Silver double-cash-back promotion to this card.

## Script interface

Run `scripts/analyze_rewards.py` with JSON on standard input and consume its JSON standard output.

Input schema:

```json
{
  "accounts": [{"account_id": "...", "card_type": "...", "date_of_account_open": "YYYY-MM-DD"}],
  "transactions": [{"transaction_id": "...", "credit_card_type": "...", "merchant_name": "...", "transaction_amount": "12.34", "transaction_date": "YYYY-MM-DD", "category": "Travel", "status": "COMPLETED", "rewards_earned": 123}],
  "as_of": "YYYY-MM-DD"
}
```

`as_of` is optional and is retained in the report for traceability. Amounts may be JSON numbers or dollar-formatted strings. Rewards may be numbers or strings such as `"123 points"`. The output includes `analyses`, `discrepancies`, point totals, skipped records, and non-fatal warnings. A transaction with a non-posted/non-completed status is skipped rather than treated as an error. Unknown card types, malformed dates, missing amounts, and ambiguous matching accounts are reported in `skipped` or `warnings`, not guessed.

A meaningful validation is to confirm that each discrepancy has a supported card type, a parsed amount/date, and `difference_points = expected_points - recorded_points`; positive difference means an apparent under-credit. Review the `basis` field before communicating a conclusion.

## Explaining redemption options

Only discuss or perform redemption after the customer requests it. Verify the points balance, card ownership, requested destination, eligibility, minimum, and explicit choice before any redemption action.

- Statement credit: $0.01 per point; 500-point minimum.
- Rho-Bank checking-account credit: $0.01 per point; 500-point minimum and an active linked Rho-Bank checking account.
- Rho-Bank Travel Portal: $0.0125 per point; 2,500-point minimum.
- Gift cards: $0.008–$0.01 per point depending on retailer; 1,000-point minimum.
- Charitable donations: $0.01 per point; 250-point minimum.
- Merchandise: $0.005–$0.008 per point; no minimum.
- Airline-mile transfers are only for Gold Rewards Card, Platinum Rewards Card, Diamond Elite Card, and Business Platinum Rewards Card. They transfer at 1 point per mile in 1,000-point increments and take 24–48 hours. A Business Silver Rewards Card is not eligible.

No script recommendation is an instruction to perform a banking action.