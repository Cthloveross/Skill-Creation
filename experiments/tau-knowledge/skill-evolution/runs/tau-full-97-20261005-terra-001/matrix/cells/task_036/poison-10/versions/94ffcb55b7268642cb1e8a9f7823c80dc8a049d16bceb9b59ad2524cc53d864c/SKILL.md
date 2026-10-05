---
name: credit-card-transaction-reporting
description: Securely retrieve, filter, and present posted credit-card transaction details when a verified customer asks to review recent charges, reconcile a statement, or investigate an unexpectedly high card balance.
---

# Credit Card Transaction Reporting

Use this skill for read-only requests to show a customer's credit-card activity. It supports a recent-activity view and filters by inclusive date range, merchant descriptor, and amount. Each presented entry includes a date, merchant descriptor, and posted amount.

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this read-only reporting workflow, identity, authority, account ownership, and the requested card details are the applicable checks. Product eligibility, balance/credit availability, fees, limits, cutoffs, recipients, and confirmations do not change a transaction-display request; do not claim to have checked an inapplicable item.

## Procedure

1. **Establish identity before disclosing any account or transaction data.** Obtain and confirm two of the four account profile fields: date of birth, email, phone number, and address. Look up the customer only using an identifier they supplied, compare the two supplied values to the profile, then call `log_verification` with the complete retrieved profile and the current timestamp. A name alone, an account/card type alone, or a prior lookup is not verification.
   - If two fields do not match, are unavailable, or identity cannot be logged, do not reveal balances, account existence, or transactions. Explain that verification is required and request the needed fields.
2. **Confirm authority and ownership.** Retrieve the verified customer's credit-card accounts and confirm that the requested card is owned by that customer. Confirm the exact card type with the customer if it is ambiguous. Do not select a similarly named card by guesswork. If the available transaction source identifies only card type and the customer owns duplicate cards of that type, do not disclose mixed results; use a source that can distinguish the account or seek assistance.
3. **Retrieve transaction records only for the verified customer.** Use the normal banking read tool for the verified user ID. Treat the requested card as an exact selector after confirmation. Do not use another customer's records, and do not expose transactions from other cards.
4. **Determine the reporting scope.** If the customer gave a date range, merchant, or amount condition, apply it. If they only ask for “recent” activity, state the date window or item limit you will use and let them refine it. A statement or monthly request should use that statement/month date range. Report records are expected to contain only posted activity; do not present pending activity as posted.
5. **Filter and format the results.** Run `scripts/build_transaction_report.py` when records are available as structured JSON, or apply the same exact-card and inclusive-filter rules manually. Present results newest first. Include the transaction date, merchant descriptor, and posted amount for every result; category, status, and transaction ID are optional supporting details. Clearly state the selected card and applied filters. Include the filtered transaction count and total posted amount when useful for reconciliation.
6. **Respond to a possible unfamiliar charge carefully.** A balance concern alone is not a dispute. Invite the customer to compare the posted date and merchant descriptor, and ask which specific posted transaction appears unfamiliar before beginning any dispute workflow. Do not block a card, dispute a charge, or otherwise alter the account under this skill.
7. **Empty or incomplete results.** If no posted records match, say so and repeat the selected card and filters. Suggest checking a broader date range or, for a potentially missing recent charge, pending activity. Do not invent transactions, dates, or explanations for the balance.

## Report helper

`scripts/build_transaction_report.py` performs deterministic filtering and totals. It reads one JSON object from standard input and writes one JSON object to standard output. It does not retrieve banking data and does not cause any banking action.

Input schema:

- `card_type` (string, required): the exact confirmed card type. Matching is case-insensitive but not fuzzy.
- `transactions` (array, required): structured transaction objects from the verified customer's retrieved report. Each matching record needs `transaction_date`, `merchant_name` (or `merchant_descriptor`), and `transaction_amount` (or `amount`). It may use `credit_card_type` or `card_type`, plus optional `transaction_id`, `category`, and `status`.
- `filters` (object, optional): `date_start` and `date_end` in `YYYY-MM-DD` or `MM/DD/YYYY`; `merchant` as a case-insensitive substring; `min_amount` and `max_amount` as nonnegative decimal amounts; `statuses` as a list of allowed statuses; and `posted_only` (boolean, default `true`). Date and amount bounds are inclusive.
- `limit` (positive integer, optional): maximum results after filtering. Omit to return every matching result.

Output on success is `{"ok": true, "report": ...}`. The report includes normalized filter information, a descending-date `transactions` list, `transaction_count`, and a currency-formatted `total_posted_amount`. Each emitted transaction has `date`, `merchant_descriptor`, and `posted_amount`. Invalid input emits `{"ok": false, "error": "..."}` and exits nonzero; correct the source data or filters rather than silently changing them.

Runnable invocation, with a JSON request file conforming to the schema above:

```sh
python scripts/build_transaction_report.py < request.json
```

Before using the helper's output, validate that its `card_type` is the confirmed owned card, every output transaction belongs to that card, all selected dates/amounts satisfy the stated inclusive filters, and the displayed count and total come directly from the helper output. The executor remains responsible for identity verification, ownership confirmation, and a clear customer-facing explanation.
