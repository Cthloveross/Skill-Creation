---
name: secure-card-transaction-review
description: Retrieve, filter, and present a customer's posted transactions for one named credit card, and safely route a subsequent report of unauthorized charges. Use for requests to see recent card charges or investigate a balance; it is not a card cancellation, replacement, or dispute-processing workflow.
---

# Secure card transaction review

Use this Skill for a read-only review of a particular credit card's activity.

## Workflow

1. Identify the customer with information they provide. If an email is needed, ask for the email associated with the account, then use `get_user_information_by_email` to obtain the `user_id`; never guess an identifier.
2. Where the normal support flow requires verification, require two customer-confirmed fields among date of birth, email, phone number, and address to match the same lookup record. Then get the current time and call `log_verification` with the complete returned record. A field visible only in a lookup response is not a customer confirmation.
3. Call `get_credit_card_accounts_by_user` for that user and confirm the requested card type exists. Match the complete card type case-insensitively; never choose a similarly named card.
4. Call `get_credit_card_transactions_by_user`. Its result may include transactions from every card the customer owns. Select locally only records whose `credit_card_type` matches the requested card before disclosing or calculating anything.
5. Honor an explicitly requested date, merchant, or amount filter. Otherwise call the selected output the recent/current activity returned by the transaction lookup—do not silently choose a statement period. Sort records newest first.
6. Give the date, merchant descriptor exactly as returned, and posted amount for every displayed record. The returned status is authoritative; describe a completed/posted record as a charge, but do not say a missing or pending record is absent. Include category/status when useful.
7. A count or total must cover exactly the displayed records, not all returned cards or an unstated period. Distinguish that total from any account current balance. If no selected records match, say so and offer another card or period.

## Deterministic filter and validation

Run `scripts/summarize_transactions.py` with JSON on stdin. Provide `card_type` and exactly one of `transactions` (a list of transaction objects) or `raw_result` (the unmodified transaction-lookup text). Optional `start_date`/`end_date` are inclusive and accept `MM/DD/YYYY` or `YYYY-MM-DD`; `merchant_query` is a case-insensitive merchant substring; `min_amount`/`max_amount` are inclusive monetary limits; and `limit` is a positive integer.

The script emits JSON with `ok`, selected `records` and `rendered_lines` newest first, plus `count`, `total`, `merchant_summary`, and `category_summary` for that exact selected set. On `ok: false`, correct the supplied input instead of interpreting it as an empty result. When reporting a count or total, run the helper on the precise displayed selection and copy its values. Verify its count equals the number of displayed records and every displayed transaction is among its records.

## Unrecognized charges and unavailable card actions

If the customer questions a transaction, first help them review its posted date and merchant descriptor. Do not label it fraud solely because it is unfamiliar. If they explicitly report a charge as unauthorized, record the identified card and applicable date, merchant, and amount.

The declared tools do not cancel, block, replace a card, or file a dispute. Do not imply any of those actions occurred. For an explicit unauthorized-charge report or card-security request, call `transfer_to_human_agents` with reason `fraud_or_security_concern` and a concise summary of the reported charges and requested help. Tell the customer that fraud/security support will assist.

## Reference use

`references/monthly_reporting_guidance.md` records the available product-specific reporting guidance. Consult it only when the requested product is exactly the product it names. For any other product, rely on the declared account/transaction tools for the read-only review and do not infer access to the reference's self-service features.
