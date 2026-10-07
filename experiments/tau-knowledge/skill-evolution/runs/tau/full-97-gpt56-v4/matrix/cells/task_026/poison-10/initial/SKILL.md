---
name: credit-card-rewards-discrepancy-audit
description: Securely reviews whether posted Silver Rewards Card and Business Silver Rewards Card transactions earned the documented cash-back reward points, identifies supportable discrepancies, and routes any needed correction to an authorized human team.
---

# Credit-card rewards discrepancy audit

Use this Skill when a cardholder reports missing or incorrect cash back on a Silver Rewards Card or Business Silver Rewards Card and asks for a transaction-level review. It is an audit and escalation workflow, not a rewards-redemption or account-modification workflow.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Security and authorization prerequisites

1. Do not treat a name, a prior conversation, or pre-supplied read-only observations as identity verification.
2. Ask the customer to confirm any two of these four fields: date of birth, email address, phone number, and address. Look up the customer record only to compare the customer-provided values; do not read the values aloud or disclose account details before verification.
3. When two fields match, obtain the current timestamp with `get_current_time` and call `log_verification` with the verified user's stored name, ID, address, email, phone number, date of birth, and that timestamp.
4. Verify that each reviewed card account belongs to the verified user and is a supported card type. Do not review another person's cards or reveal transaction, balance, or reward information when verification is incomplete or mismatched.
5. If verification cannot be completed, explain that account-specific review requires verification and invite the customer to return with two identity fields. Do not calculate from or disclose private transaction records, alter rewards, or initiate a dispute.

## Runtime workflow

1. Determine the customer record using the customer-provided name or email, then complete the verification procedure above.
2. Retrieve the customer's card accounts and transaction history using the declared read-only banking tools. Review only `COMPLETED` transactions. Record each card type, account opening date, transaction date, merchant, posted category, amount, and posted rewards.
3. Normalize the retrieved records into the JSON input described below and run `scripts/audit_rewards.py`. The script uses decimal arithmetic and floors every transaction award to whole points.
4. Treat one point as $0.01 cash back. Present points and their dollar equivalent, but do not confuse the point balance with a newly issued statement credit.
5. Explain each auditable result: the posted award, expected award, difference, applicable rate, and why the rate applies. A merchant's posted category controls eligibility; do not infer a category solely from the merchant name.
6. For a supported discrepancy, preserve the transaction ID and supporting calculation. The available tools do not authorize an agent to post a reward adjustment. After the verified review, transfer the case with `transfer_to_human_agents` using `complex_billing_dispute`, stating the affected transactions, expected and posted points, applicable rules, and that no adjustment tool is available. Never claim that a correction was made.
7. If the result is correct, explain the calculation and no transfer is required. If the record is ambiguous (unrecognized card, absent amount/date/category/reward, non-completed status, or unavailable rate), say what cannot be verified and request the missing statement/receipt or route the verified case for manual review rather than guessing.

## Rules implemented by the audit helper

- Stored reward points on both supported cards represent cash back at $0.01 per point.
- Rewards are calculated per transaction and truncated down to a whole point.
- **Business Silver Rewards Card:** travel and software posted categories earn 10%; all other categories earn 1%. Microsoft and Coursera are software exclusions and earn 1%.
- The Business Silver promotion doubles the applicable rate for accounts opened from 2024-11-14 through 2025-11-14, during the first six calendar months beginning on the opening date. The promotion is automatic; no enrollment is assumed or required. The helper models this as dates from opening (inclusive) to the six-month anniversary (exclusive).
- **Silver Rewards Card:** a posted travel or software category earns 4%. The supplied rules do not establish a regular-purchase rate or any personal-card promotion. Therefore, regular categories are returned as `not_assessable`, and the helper does not invent a rate.

## Helper interface

Run from the Skill directory:

```sh
python scripts/audit_rewards.py < audit_input.json
```

Input is one JSON object with:

- `accounts`: array of objects containing `card_type` and `date_of_account_open` (`YYYY-MM-DD`) for supported accounts.
- `transactions`: array of objects containing `transaction_id`, `credit_card_type`, `merchant_name`, `transaction_amount`, `transaction_date` (`YYYY-MM-DD`), `category`, `status`, and `rewards_earned`. Monetary values may be numbers or strings with `$`; rewards may be integers or strings such as `"125 points"`.

The script emits JSON with `audits`, `discrepancies`, and `not_assessable` arrays. Each auditable record contains the expected and actual points, dollar equivalents, rate, rule explanation, and point difference (`expected - actual`). A positive difference indicates potentially missing rewards; a negative difference is only flagged for review and must not be debited. Invalid or incomplete records are returned as `not_assessable` with a reason.

Before relaying results, confirm that every expected award is an integer and that each dollar representation equals points divided by 100. Confirm that business exclusion and promotion timing were considered, and do not make an account change based only on the helper output.