---
name: credit-card-transaction-dispute-filing
description: Verify a credit-card customer, resolve reported posted transactions, assess provisional-credit eligibility, and file one formal dispute per selected transaction. Use for fraud, duplicate charges, billing errors, merchandise or service issues, cancelled subscriptions, and unprocessed refunds.
---

# Credit Card Transaction Dispute Filing

Use this Skill for formal disputes of posted credit-card transactions. Each selected transaction requires its own `file_credit_card_transaction_dispute_4829` call, including when several charges concern the same card or merchant.

## Workflow

1. **Verify identity before account-specific processing or filing.** Have the customer confirm at least two registered identity fields among date of birth, email, phone number, and address. Compare against the canonical user record. After two fields match, obtain the current timestamp and call `log_verification` with the canonical profile fields and timestamp. A name or account lookup alone is not verification.
2. Retrieve the customer's credit-card accounts and transaction history. Match every reported charge to exactly one posted transaction using the intended card, merchant, amount, and purchase date. If the match is missing or ambiguous, ask for clarification rather than guessing a transaction ID.
3. Retrieve the last four digits for every affected account using the documented `get_card_last_4_digits(credit_card_account_id)` discovered tool. Use the runtime discovery/unlock process applicable to agent tools. Never request or expose a full card number.
4. For each selected transaction, collect and normalize:
   - dispute reason;
   - whether the merchant was contacted;
   - issue-noticed date;
   - requested resolution; and
   - a positive partial-refund amount only when the requested resolution remains `partial_refund`.

   If the customer says “today,” obtain the runtime current time and use that calendar date in `MM/DD/YYYY` form.
5. Retrieve the verified user's dispute history with `get_user_dispute_history_7291`. Count prior disputes in the 12 months ending on the current date. A successfully retrieved empty list means zero; a failed, partial, or ambiguous lookup is not evidence of zero.
6. Determine provisional-credit eligibility independently for each claim. Ineligibility does not prevent filing: submit the dispute with `eligible_for_provisional_credit: false`.
7. Run `scripts/prepare_disputes.py` with the verified profile, accounts, successfully retrieved history, and all currently selected claims. Resolve any claim-specific validation error before filing that claim.
8. Unlock `file_credit_card_transaction_dispute_4829`, then submit each generated `tool_arguments` object once through `call_discoverable_agent_tool`. Its outer `arguments` parameter must be a JSON string representing that object. Record the result for every call.
9. Before reporting completion, run `scripts/reconcile_filings.py`. It must show no selected transaction without a confirmed successful filing. Retry an unconfirmed filing when operationally appropriate, or preserve and escalate its failure; never state that it was filed without a successful tool result.

Do not use `apply_statement_credit_8472` instead of a dispute filing. A statement credit is not a formal dispute and does not implement provisional credit.

## Late clarifications and changed resolutions

Maintain a claim ledger from the customer's final instructions: one row per selected transaction, its current resolution, and its filing result. Customer clarifications supersede an earlier unresolved instruction for the same transaction.

In particular, if a customer originally selected `partial_refund` but could not provide an amount, leave that claim unfiled while obtaining clarification. If the customer later changes that request to `full_refund` or `reversal_of_charge`, remove the partial-refund amount, update the claim, rerun preparation for that claim, and formally file it. Do not silently drop the transaction because its earlier partial-refund request was incomplete. Do not create a second filing when an earlier filing already succeeded; reconcile the ledger first.

## Exact filing values

Only use these values:

- `card_action`: `keep_active`, `cancel_and_reissue`
- `dispute_reason`: `unauthorized_fraudulent_charge`, `duplicate_charge`, `incorrect_amount`, `goods_services_not_received`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, `refund_never_processed`
- `resolution_requested`: `full_refund`, `partial_refund`, `reversal_of_charge`

Set `card_action` from the customer's explicit preference. Use `keep_active` if they wish to retain the card. Use `cancel_and_reissue` only if they elect cancellation and reissue, including a replacement already ordered through the separate replacement workflow. Do not infer that fraud requires replacement.

`contacted_merchant` must faithfully record the customer's answer. For non-fraud disputes, contact with the merchant is required for provisional-credit eligibility but not for the ability to formally file the dispute.

## Provisional-credit assessment

Set `eligible_for_provisional_credit` to `true` only when all conditions below hold:

1. The account has been open at least 60 days.
2. The reason is `unauthorized_fraudulent_charge`, `duplicate_charge`, or `goods_services_not_received`. A not-received claim also requires a purchase more than 30 days before the current date.
3. The full transaction amount is at least $25 and does not exceed the documented card-tier maximum.
4. The customer has not filed more than two disputes in the previous 12 months.
5. For a non-fraud eligible reason, the customer contacted the merchant.

Maximums are Entry $2,500, Mid $5,000, Premium $10,000, Elite $15,000, and Invitation $25,000. Gold Rewards Card and Business Gold Rewards Card are Premium. If account age, tier, current date, transaction amount, or dispute history cannot be reliably evaluated, do not claim eligibility; obtain the missing data or use `false` with the unresolved basis documented according to normal operations.

Reasons `incorrect_amount`, `goods_services_not_as_described`, `canceled_subscription_still_charging`, and `refund_never_processed` are explicitly ineligible. A formal filing is still required when the customer requests one.

## Preparation helper

`scripts/prepare_disputes.py` reads one JSON object from stdin and emits one JSON object on stdout. It performs no banking action.

Input schema:

```json
{
  "current_date": "MM/DD/YYYY",
  "profile": {
    "full_name": "...",
    "user_id": "...",
    "phone": "...",
    "email": "...",
    "address": "..."
  },
  "accounts": [
    {
      "account_id": "...",
      "card_type": "Gold Rewards Card",
      "opened_date": "MM/DD/YYYY",
      "last4": "1234"
    }
  ],
  "prior_disputes": [{"dispute_date": "MM/DD/YYYY"}],
  "claims": [
    {
      "transaction_id": "...",
      "account_id": "...",
      "transaction_amount": 100.0,
      "purchase_date": "MM/DD/YYYY",
      "issue_noticed_date": "MM/DD/YYYY",
      "dispute_reason": "duplicate_charge",
      "contacted_merchant": true,
      "resolution_requested": "full_refund",
      "card_action": "keep_active"
    }
  ]
}
```

Claims must already be uniquely matched to transaction-history data. For `partial_refund`, add `partial_refund_amount`; omit it for all other resolutions. Account opening dates and history dates may be supplied in ISO date form, but filing dates are emitted in required `MM/DD/YYYY` form.

The output contains `ok`, claim-specific `errors`, `prior_disputes_last_12_months`, and `submissions`. Each submission contains the exact filing payload in `tool_arguments` plus an eligibility explanation. `ok` is true only when all supplied claims are ready. Do not submit a claim absent from `submissions`.

Example: `python3 scripts/prepare_disputes.py < input.json`

## Filing reconciliation helper

After calls return, pass every transaction the customer currently selected and the observed filing outcomes to `scripts/reconcile_filings.py`:

```json
{
  "selected_transaction_ids": ["..."],
  "filings": [
    {"transaction_id": "...", "success": true}
  ]
}
```

It emits `ok`, `missing_or_unsuccessful`, `duplicate_selected_ids`, and `invalid_filings`. Treat `success` as true only for a non-error tool result that confirms the dispute was filed successfully. Example: `python3 scripts/reconcile_filings.py < filings.json`.

## Failure handling and customer completion

- Stop account-specific action if identity verification fails.
- Do not file against a similar transaction when the reported charge cannot be uniquely resolved.
- If suffix or dispute-history retrieval fails, retry or escalate under normal procedures rather than guessing.
- If a filing call fails, do not call it filed. Preserve the failure context for retry or escalation.
- Confirm each successfully filed dispute and whether provisional credit was eligible. Explain that provisional credit is temporary and can be reversed after investigation.
