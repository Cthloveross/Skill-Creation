---
name: cash-back-discrepancy-audit
version: 1.0.0
description: Audit posted Business Silver Rewards Card and Silver Rewards Card transactions for likely cash-back discrepancies, explain rate eligibility, and safely guide dispute submission or approved reward correction.
---

# Cash-Back Discrepancy Audit

Use this Skill when a cardholder reports missing or incorrect cash back on a Business Silver Rewards Card or Silver Rewards Card and transaction/account data is available through the normal banking tools.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Safety and prerequisites

1. Verify the customer using two of the four identity fields (date of birth, email, phone number, address) and call `log_verification` only after both match the customer record. A name alone is not sufficient.
2. Confirm that each reviewed account belongs to the verified customer and that the transaction belongs to the indicated card type. Use only posted/completed purchases for a final rewards calculation.
3. This Skill can identify likely discrepancies, but it does **not** authorize changing rewards. Do not unlock or call an internal reward-update tool unless there is a resolved, approved dispute record for the exact transaction and the correction procedure permits the update.
4. Do not use a statement credit as a substitute for correcting transaction rewards. A cash-back discrepancy should follow the dispute/correction process.
5. If category coding, purchase status, amount, account opening date, or promotion eligibility is unavailable or ambiguous, label the finding as tentative and seek the missing record rather than assuming a bonus rate.

## Reward rules implemented

All calculated rewards are whole-number database points. For these cash-back cards, 1 point represents $0.01 in cash back. Compute points as `floor(amount_in_dollars × cash_back_rate × 100)`; never round fractional points up.

### Business Silver Rewards Card

- Travel and Software/SaaS merchant categories earn 10%; all other purchases earn 1%.
- The category submitted by the merchant controls eligibility. Travel and Software categories are eligible only when not subject to a listed exclusion.
- The following named merchants receive the standard rate even when the category is Travel or Software: Concur, SAP Concur, Expensify, Navan, Apple, Microsoft, Dell, Xbox Game Pass, PlayStation Plus, Nintendo Switch Online, Coursera, Udemy, LinkedIn Learning, Skillshare, and Pluralsight.
- A customer who opened the card from 2024-11-14 through 2025-11-14 receives double the otherwise applicable rate for the six calendar months beginning on their account-opening date. The doubled rates are therefore 20% for otherwise eligible Travel/Software purchases and 2% for other or excluded purchases. No enrollment is required.

### Silver Rewards Card

- Travel and Software/SaaS merchant categories earn 4%; other purchases earn 1%.
- Eligibility still depends on merchant category. Third-party processors, onboard retail/food purchases, some vacation rentals, and merchants not coded as Travel or Software may earn the standard rate.
- The Business Silver merchant-exclusion list is not applied to this card unless independent, applicable policy says otherwise.

## Runtime workflow

1. Obtain the verified user's card accounts with `get_credit_card_accounts_by_user` and transactions with `get_credit_card_transactions_by_user`.
2. Transcribe the returned records into the JSON schema below and run `scripts/rewards_audit.py`. The helper is read-only and makes no banking calls.
3. Review every item whose `finding` is `under_awarded`, `over_awarded`, `unavailable`, or `needs_review`. Recheck the source amount, posted status, merchant category, card type, account opening date, and actual stored points before communicating a conclusion.
4. Explain confirmed likely shortfalls in points and dollars (points divided by 100). Explain exclusions or non-qualifying category coding plainly. For a possible merchant miscoding, advise that receipts and confirmations can support a category review.
5. For a customer-initiated cash-back dispute, provide the user-facing tool `submit_cash_back_dispute_0589(user_id: str, transaction_id: str)` through `give_discoverable_user_tool`. Confirm the exact transaction ID first. The user, not the agent, executes that tool.
6. If an approved/resolved dispute record later identifies transactions needing correction, independently rerun this calculation. Then follow the approved internal correction workflow: unlock `update_transaction_rewards_3847`, submit each exact `transaction_id` and `new_rewards_earned` formatted as `"X points"`, and confirm the resulting value in transaction history. Record the independent calculation and prerequisites in the case record.
7. If no transaction can be identified or the customer cannot complete verification, do not expose account-specific findings or change anything. Ask for two verification fields and, after verification, a statement period, merchant, amount, or transaction ID.

## Helper input and output

Run with JSON on standard input, for example:

```sh
python3 scripts/rewards_audit.py <<'JSON'
{"accounts":[{"card_type":"Business Silver Rewards Card","date_of_account_open":"YYYY-MM-DD"}],"transactions":[{"transaction_id":"...","credit_card_type":"Business Silver Rewards Card","merchant_name":"...","transaction_amount":"0.00","transaction_date":"YYYY-MM-DD","category":"Travel","status":"COMPLETED","rewards_earned":"0 points"}]}
JSON
```

Input object fields:

- `accounts`: array of account objects with `card_type` and `date_of_account_open` (`YYYY-MM-DD`).
- `transactions`: array with `transaction_id`, `credit_card_type`, `merchant_name`, `transaction_amount`, `transaction_date`, `category`, `status`, and `rewards_earned`. Monetary values may be JSON numbers or dollar-formatted strings; actual rewards may be an integer or a string such as `"125 points"`.

The output contains `audits` and a `summary`. Each usable audit includes the expected whole points, actual points, point and dollar difference, applied rate, whether the Business Silver promotion applied, eligibility rationale, and a `finding`. A positive difference means the stored rewards are below the calculated amount. Unsupported cards, malformed values, non-posted items, refunds, and transactions predating their account opening date are not assigned an expected reward and are explicitly flagged for review.

Before relying on output, validate that each reviewed audit has the same transaction ID, amount, card type, category, and actual points as the source record. Confirm that `expected_points` is an integer and that `difference_points` equals `expected_points - actual_points` when both are present.
