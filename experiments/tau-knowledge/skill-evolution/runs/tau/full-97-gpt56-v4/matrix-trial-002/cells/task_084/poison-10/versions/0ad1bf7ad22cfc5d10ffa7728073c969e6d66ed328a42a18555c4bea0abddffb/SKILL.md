---
name: debit-card-transaction-dispute
version: 1.0.3
description: Safely gather, validate, file, and follow up on Regulation E debit-card transaction disputes, including duplicate charges, fraud categorization, provisional-credit determination, and required card actions.
---

# Debit-Card Transaction Dispute

Use this Skill when a verified customer requests a dispute involving a debit-card purchase, ATM transaction, recurring debit-card payment, or debit-card P2P transfer. It is a workflow aid: it validates supplied facts and recommends tool payloads; the executor must use the normal banking tools to retrieve data and perform any bank action.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Required facts and customer communication

1. Verify the customer before retrieving or filing anything. Confirm at least two identity fields through the available user lookup tools, obtain the current time, and log the verification using `log_verification` when that tool is available.
2. Before filing an unauthorized-activity dispute, explain the applicable Regulation E exposure based on when the customer noticed the activity relative to their statement: within 2 business days: maximum $50; within 60 days: maximum $500; after 60 days: potentially unlimited liability and funds may not be recoverable. Do not claim a band unless the statement/discovery timing supports it. When the filing runtime requires a customer maximum-liability field, use the applicable statutory band exactly: `50`, `500`, or `-1` for unlimited liability. This exposure value is not capped to the disputed amount and is distinct from any provisional-credit offset.
3. For every requested dispute, collect:
   - merchant or ATM, date, amount, and what happened;
   - date first noticed (`discovery_date`) and enough statement/report timing to establish the Regulation E liability band;
   - transaction channel (PIN/signature in-store, online/phone, ATM withdrawal/deposit, recurring, or P2P);
   - whether fraud is suspected and, if so, whether the card was physically present;
   - whether the card remains in the customer's possession;
   - PIN status: shared, observed/skimming suspected, not compromised, or unknown;
   - whether the merchant was contacted for non-fraud claims;
   - for fraud over $500, whether a police report was filed; recommend one if not;
   - consent to use the conversation as the written statement;
   - ATM identity and whether it is a Rho-Bank or third-party ATM, for ATM claims.
4. If required facts are missing, ask only for the missing facts and do not file yet. In particular, the customer statement that a charge is duplicate does not establish transaction type, discovery date, card possession, PIN status, merchant-contact status, or written-statement consent.

## Retrieve and check bank records

After verification, unlock and use the applicable normal banking tools documented by the environment:

1. Use `get_all_user_accounts_by_user_id_3847(user_id)`. Identify the customer-owned checking account named or otherwise matched by the customer. It must be `OPEN`; record account ID, class/tier, opening date, balance, and any stated holds/restrictions.
2. Use `get_debit_cards_by_account_id_7823(account_id)`. Match the card ID and last four digits to the customer’s card and confirm that it is linked to the selected checking account. Record card status and details. Do not select an old closed card merely because the last four digits were mentioned.
3. Use `get_bank_account_transactions_9173(account_id)`. Match the claimed transaction by date, amount, description, debit sign, and posted/pending status. Use the actual `transaction_id`, date, and absolute debit amount. Transactions are reverse chronological.
4. Determine the number of currently open disputes **for that account**, not for the customer. The maximum is Entry 2, Mid 3, Premium 4, Elite 5. If the supported runtime has no authorized source for that count, do not guess or file; obtain it through the bank’s approved workflow or escalate.
5. Confirm the transaction is at least $1.00 and no more than 60 days old. If it is ineligible, explain the relevant limitation and do not call the filing tool.
6. For duplicate charges, identify all matching duplicate candidates and dispute the earliest (first) transaction, even if another duplicate is more recent.

Use `scripts/dispute_helper.py` to consistently validate gathered data and construct a proposed filing payload. It does not query the bank and does not perform a banking action.

## Classification and filing

Map the circumstances exactly:

| Circumstance | `dispute_category` |
|---|---|
| Unauthorized but fraud not suspected | `unauthorized_transaction` |
| ATM gave wrong/no cash | `atm_cash_discrepancy` |
| ATM deposit missing | `atm_deposit_not_credited` |
| Same transaction charged multiple times | `duplicate_charge` |
| Amount differs from expected | `incorrect_amount` |
| Goods/services never received | `goods_services_not_received` |
| Charge continues after cancellation | `recurring_charge_after_cancellation` |
| Suspected fraud, physical/card-present transaction | `card_present_fraud` |
| Suspected fraud, online/phone/card-not-present transaction | `card_not_present_fraud` |

Use exactly one transaction type: `pin_purchase`, `signature_purchase`, `online_purchase`, `atm_withdrawal`, `atm_deposit`, `recurring_payment`, or `person_to_person`.

The per-dispute `card_action` is fixed by category:

- `card_present_fraud`, `card_not_present_fraud` → `close_and_reissue`
- `unauthorized_transaction` → `freeze_pending_investigation`
- all other allowed categories → `keep_active`

Only after all checks pass, unlock and call `file_debit_card_transaction_dispute_6281` with the helper’s proposed payload, after confirming every field reflects the customer’s information. The required payload contains transaction ID, account/card/user IDs, category, transaction and discovery dates in `MM/DD/YYYY`, positive float disputed amount, transaction type, card possession, PIN status, merchant-contact flag, police-report flag, written-statement flag, provisional-credit eligibility, the runtime-required customer maximum-liability amount when exposed, and per-dispute card action. Never omit a required runtime field merely because it was absent from a generic workflow summary.

Do not infer a written statement from the conversation without the customer’s agreement. Do not substitute `unauthorized_transaction` for suspected fraud. Do not file more than the permitted open-dispute count.

## Provisional credit and completion

Provisional credit is required only when all applicable conditions are satisfied: timely report within 60 days of the statement, a qualifying category (`unauthorized_transaction`, either fraud category, `atm_cash_discrepancy`, or `duplicate_charge`), written statement, and an OPEN account with no hold/restriction. It is not required for the other categories; it is also not required when a non-fraud merchant was not contacted, when the PIN was voluntarily shared, or for a new account (under 30 days) with card-not-present fraud. The helper reports the deterministic result from supplied facts.

For an eligible claim, provisional credit is the full disputed amount less a supported $50/$500 late-report liability offset, never below zero. Tell the customer the expected timing: within 10 business days normally, or 20 for an account open less than 30 days. With provisional credit, investigations are generally 45 business days and can be 90 for international/foreign merchant POS, new accounts, or applicable extended cases. Do not promise provisional credit when the requirements are not established.

For multiple filings on one card, retain each filing’s own `card_action`. After all filings succeed, carry out only the single most severe actual card action for that card: `close_and_reissue` over `freeze_pending_investigation` over `keep_active`. Unlock and use only an action tool explicitly supported by the runtime; for example, the documented freeze action is `freeze_debit_card_3892`. Never treat a metadata field as having performed the action. If a necessary action tool is not exposed, do not leave a fraud-related close/reissue action unaddressed: use `transfer_to_human_agents` with reason `fraud_or_security_concern`, summarizing the filed disputes and the required single card action. If neither the action tool nor an approved escalation path is available, tell the customer what remains pending rather than claiming completion.

Conclude with the filed dispute identifiers/results, any card action actually completed, provisional-credit status and timing, investigation expectations, and any remaining requested disputes that still need details.

## Helper interface

Run:

```sh
python3 scripts/dispute_helper.py <<'JSON'
{
  "as_of_date": "MM/DD/YYYY",
  "account": {"account_id": "...", "status": "OPEN", "tier": "Premium", "date_opened": "MM/DD/YYYY", "has_hold_or_restriction": false, "open_dispute_count": 0},
  "card": {"card_id": "...", "account_id": "...", "user_id": "..."},
  "disputes": [{"transaction_id": "...", "transaction_date": "MM/DD/YYYY", "amount": 12.34, "category": "duplicate_charge", "transaction_type": "signature_purchase", "discovery_date": "MM/DD/YYYY", "card_in_possession": true, "pin_compromised": "no", "contacted_merchant": true, "police_report_filed": false, "written_statement_provided": true, "timely_reported_within_60_days_of_statement": true, "liability_band": "within_2_business_days", "liability_offset": 0}]
}
JSON
```

It emits JSON with `ok`, `errors`, `warnings`, and a result per supplied dispute. Each result contains `proposed_filing_payload` only when validation passes, plus provisional-credit reasoning and amount. Validate that `ok` is true and review warnings before filing. The helper deliberately rejects missing identifiers, invalid dates/enums (including an unknown liability band), amounts below $1, transactions older than 60 days, non-open accounts, card/account mismatch, and tier-limit overflow.
