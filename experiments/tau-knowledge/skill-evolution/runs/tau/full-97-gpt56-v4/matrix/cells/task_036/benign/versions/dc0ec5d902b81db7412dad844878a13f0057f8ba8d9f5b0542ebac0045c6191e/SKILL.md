---
name: secure-credit-card-transaction-review
description: Securely verify a customer, retrieve and present posted transactions for one named credit card, and route reported unauthorized activity to fraud support. Use for requests to review card charges, reconcile a statement, investigate a higher balance, or report unfamiliar transactions; do not use it to perform cancellation, replacement, or a dispute when the required action tool is unavailable.
---

# Secure credit-card transaction review

Use this Skill for a customer who wants transaction activity for a specified credit card. It covers the read-only review and the safe handoff if that review reveals suspected fraud.

## Privacy and verification prerequisite

Transaction and card-account details are sensitive. Do not disclose balances, card types, transaction records, or whether a specific charge exists until the customer has confirmed **two of these four fields**: date of birth, email address, phone number, or address.

1. Ask for the needed identifying fields without supplying values from the account record. An email can be used to locate a possible record, but it is only one confirmed field when the customer provided it.
2. Look up the customer using the applicable declared lookup tool. Compare each customer-supplied field with the returned record. A mismatch, no record, or an ambiguous match is not verification; ask for a correction or use the normal support path without exposing account information.
3. Once two fields match the same record, obtain the current time with `get_current_time` and call `log_verification` with the returned complete record and that timestamp. Do this before fetching or presenting card information.
4. Do not treat a field merely seen in a lookup response as customer confirmation. Never reveal the other fields to obtain confirmation.

A transfer for a suspected security incident may be made without disclosing protected account data when a supported fraud transfer path is available.

## Reviewing the requested card

After verification:

1. Use `get_credit_card_accounts_by_user` and confirm that the requested card type exists. Match the card type exactly except for capitalization. Do not substitute a similarly named card.
2. Use `get_credit_card_transactions_by_user` for that user. The response contains activity for all of the customer’s cards: filter locally to the selected card type before any presentation.
3. Treat the returned status as authoritative. Describe posted/completed records as charges. Do not say missing or pending items are absent; reporting data only includes items once they post.
4. Honor a date range supplied by the customer. Otherwise describe the output as the recent/current activity returned by the lookup, rather than silently inventing a statement period. Sort selected records newest first.
5. State each selected transaction’s date, merchant descriptor exactly as returned, and posted amount. Category and status may be included. If reporting a count or total, calculate it only from exactly the displayed records and say that it is not the current account balance. Do not reveal records belonging to another card.
6. If no selected-card records match, say so and offer to check a different period or card.

The included helper only analyzes supplied transaction data. It does not call banking tools and cannot authorize a bank action.

## Report helper

Run `scripts/summarize_transactions.py` with one JSON object on stdin:

```json
{
  "card_type": "<requested card type>",
  "transactions": [
    {
      "transaction_id": "<id>",
      "credit_card_type": "<card type>",
      "merchant_name": "<merchant descriptor>",
      "transaction_amount": "$12.34",
      "transaction_date": "MM/DD/YYYY",
      "category": "<category>",
      "status": "COMPLETED"
    }
  ],
  "start_date": "MM/DD/YYYY",
  "end_date": "MM/DD/YYYY",
  "limit": 10
}
```

Provide exactly one of `transactions` (a list of transaction objects) or `raw_result` (the line-oriented text returned by `get_credit_card_transactions_by_user`). Date bounds are optional, inclusive, and accept `MM/DD/YYYY` or `YYYY-MM-DD`; `limit` is an optional positive integer. Omit `limit` to retain every matching record. The output is JSON:

```json
{"ok": true, "card_type": "...", "date_range": {"start_date": null, "end_date": null}, "count": 0, "total": "$0.00", "records": [], "rendered_lines": []}
```

Records are newest first. If input is malformed or bounds are invalid, it emits `{"ok": false, "error": "..."}`; correct the input rather than treating an error as an empty report.

Before replying, verify that every displayed record has the selected card type and falls within any requested bounds, and that its displayed count and total match the same displayed set.

## Suspected unauthorized activity or card-security request

If, after a review, the customer says a charge is not theirs, treat that as a reported security concern. Do not dismiss it based on a merchant descriptor and do not claim it is fraud as a proven fact. Capture the card type and the date, merchant descriptor, and amount of each charge the customer identifies, when available.

Cancellation, card blocking, replacement issuance, and dispute filing require their own authorized workflow. Do **not** promise that a card was cancelled, replaced, blocked, or that a charge was disputed unless a declared tool completed that exact action. If the declared normal tools do not provide the requested security action, call `transfer_to_human_agents` with reason `fraud_or_security_concern` and a concise summary of the reported unauthorized charges and the customer’s requested action. Then tell the customer that their case has been transferred to fraud/security support for assistance. Do not disclose extra account or transaction data in the transfer summary.

## Self-service reporting option

For a customer who only wants recordkeeping help, they can sign in to the Reports or Statements section, select a current or past statement period, apply date, merchant, or amount filters, and download available CSV or PDF reports. This option does not replace an urgent fraud/security handoff.
