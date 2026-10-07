---
name: business-silver-cash-back-review
description: Review a verified customer's Business Silver Rewards Card transactions for possible cash-back discrepancies. Use when a customer questions travel or software rewards, including the account-opening-based double-cash-back promotion and stated merchant exclusions.
---

# Business Silver Rewards cash-back review

Use this Skill to investigate a reported rewards issue without exposing account details before identity verification. It applies only to the **Business Silver Rewards Card** rules supplied with this package. Do not apply its rates to another card product.

## Required customer-service flow

1. Acknowledge the concern and ask which transaction(s) or statement period the customer wants reviewed. If the customer has not supplied a full name or account email, ask for one.
2. Look up the customer using the supplied name or email. Do not reveal the returned email, address, phone number, date of birth, account balance, transactions, or reward totals yet.
3. Verify identity before discussing account-specific results:
   - Ask the customer to provide any **two** of these four fields: date of birth, email address, phone number, and street address.
   - Compare their supplied values with the lookup result. Do not treat data volunteered by the agent or merely displayed by the lookup as customer confirmation.
   - If two fields match, call `get_current_time` and then `log_verification` with the complete returned identity record and that timestamp. If verification fails or is incomplete, politely ask for another field and do not disclose account information.
4. After verification, call `get_credit_card_accounts_by_user` and `get_credit_card_transactions_by_user`. Select the account whose `card_type` is exactly `Business Silver Rewards Card`; do not combine it with similarly named personal cards.
5. Convert the relevant account and completed transactions into the JSON input for `scripts/analyze_business_silver.py`. Run it through `run_skill_script`.
6. Explain the results in customer-friendly terms. State the transaction date, merchant, posted reward, expected rate and reward, and any calculated shortfall for each flagged transaction. Points on this cash-back card equal $0.01 each. Make clear that merchant-category coding controls whether travel/software earns the bonus.
7. For a transaction flagged as a possible shortfall, explain that the records support a rewards review. Preserve the transaction identifiers and the analyzer result for the normal support workflow. If the available runtime exposes an authorized adjustment/review action and its documented prerequisites are met, use that documented action. Otherwise, do **not** claim an adjustment, investigation case, or credit was created; tell the customer that the transaction requires a customer-service review and, if the issue cannot be completed in the current channel, transfer using the applicable declared transfer reason.

## Policy encoded by the analyzer

- Eligible travel and software coding earns 10% cash back; all other purchases earn 1%.
- Concur, SAP Concur, Expensify, Navan, Apple, Microsoft, Dell, Xbox Game Pass, PlayStation Plus, Nintendo Switch Online, Coursera, Udemy, LinkedIn Learning, Skillshare, and Pluralsight receive the standard 1% rate rather than the 10% bonus.
- A customer who opened the account during the offer dates (2024-11-14 through 2025-11-14) receives double the otherwise applicable rate during the six calendar months beginning on their account-opening date. The analyzer models this as dates from the opening date through, but excluding, the same day six calendar months later.
- Merchant labels and the stored category are evidence, not a substitute for a merchant-category investigation. Treat an unfamiliar or disputed category as requiring review rather than promising a bonus.

## Analyzer interface

Run:

```text
run_skill_script(relative_path="scripts/analyze_business_silver.py", input_json={
  "accounts": [{"account_id": "...", "card_type": "Business Silver Rewards Card", "date_of_account_open": "YYYY-MM-DD"}],
  "transactions": [{"transaction_id": "...", "credit_card_type": "Business Silver Rewards Card", "merchant_name": "...", "transaction_amount": "0.00", "transaction_date": "YYYY-MM-DD", "category": "Travel", "status": "COMPLETED", "rewards_earned": 0}]
})
```

The script emits JSON with `reviewed_transactions`, `possible_shortfalls`, totals in points and dollars, skipped records, and validation `errors`. It intentionally does not use customer names, contact details, balances, or account reward totals. Inspect `errors` before relying on a result. Only completed transactions for the selected card are evaluated. The script rounds expected reward points to the nearest whole point using half-up rounding; if a posted record uses a different documented rounding convention, route that edge case for review rather than asserting an adjustment.

## Final response checklist

- Confirm the verified card and scope reviewed.
- Separate normal transactions, exclusions, and potential shortfalls.
- Explain promo timing only from the account opening date and transaction date.
- Present points and dollar equivalents accurately (100 points = $1.00).
- Do not imply that a merchant is eligible solely because of its name, and do not promise or perform an unsupported account change.
