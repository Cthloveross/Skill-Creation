---
name: credit-card-transaction-review
version: 1.2.0
description: Retrieve and clearly present recent posted transactions for one customer-selected credit card, help the customer identify unfamiliar records, and safely escalate an explicit unauthorized-charge or card-security report. Use for read-only statement, charge-review, and follow-up unfamiliar-charge requests.
---

# Credit-card transaction review

Use this Skill when a customer asks to see charges, review statement activity, understand a credit-card balance, or subsequently identifies displayed charges as unfamiliar. Start as a read-only review. Do not alter account details, file a dispute, cancel a card, or promise a replacement unless a declared banking tool and applicable policy explicitly support that action.

## Retrieve the correct card activity

Obtain only what is needed through the normal banking tools:

1. Identify the customer using an identifier supplied by the customer. If none is available, request an exact full name, user ID, or email. Resolve it with the corresponding user lookup tool.
2. Call `get_credit_card_accounts_by_user` and locate the requested card by exact `card_type`. If no exact card is returned, say so. If several cards could reasonably match the customer's wording, ask which card they mean; do not choose a different card merely because its name is similar.
3. Call `get_credit_card_transactions_by_user`. Retain only records whose `credit_card_type` exactly matches the selected card type.
4. Use current time only if it is necessary to explain a requested date period. Do not call a completed charge pending, and do not infer an unreturned charge, payment, credit, fee, or interest item.

No identity-verification or account-changing tool call is needed solely to provide this read-only report unless a separately supplied policy requires it.

## Report the result accurately

State the selected card and its returned current balance, if present. List matching records newest first and include each record's date, merchant descriptor, amount, category, and status when returned. Describe the output as the matching activity returned by the lookup, not as a complete statement reconciliation.

For a short result set, show all matching records. For a long result set, show a useful newest subset, state both the number shown and the number matched, and offer to narrow by a date range, merchant, or amount. If the customer says “recent” but needs a particular statement period, ask for the month or date range. If no matching records are returned, say so and offer the same filters. Never mix activity from another card.

For a balance concern, say only that the returned transactions may not fully explain the balance because earlier posted activity, payments, credits, fees, or interest can affect it. Do not imply that any such item exists in this customer's account.

## Unfamiliar-charge follow-up and safe escalation

If the customer merely says a record looks unfamiliar, identify the returned date, merchant descriptor, amount, and status and invite them to review those details. This follows the supplied reporting guidance to review a posted date and merchant descriptor before a dispute is considered. Do not label the transaction fraudulent based on unfamiliarity alone.

If, after that review, the customer explicitly says a charge is unauthorized, alleges stolen card information, or requests immediate security action:

1. Acknowledge the concern without asserting that theft or fraud has been confirmed.
2. Preserve the exact charge details already returned (date, merchant, amount, selected card) in the transfer summary. State what was and was not done.
3. Do **not** file a dispute, cancel the card, replace it, or make account changes using tools that do not declare those capabilities.
4. Escalate with `transfer_to_human_agents` using `reason: "fraud_or_security_concern"`. After a successful transfer, tell the customer a human agent will assist shortly. Do not submit a duplicate transfer if one has already succeeded.
5. If the customer then requests cancellation or replacement but no declared tool supports it, say that this chat cannot perform that action and direct them to the already-escalated human agent. Do not promise a particular outcome.

## Scope of the supplied product information

The supplied documentation establishes monthly reporting, report filters, and CSV/PDF export for the **Bronze Rewards Card**. Mention the Reports or Statements workflow, filtering, or export only when the selected card is Bronze Rewards Card (or when separately supplied evidence establishes the same feature for the selected product). Do not generalize that product-specific documentation to a different card type. Direct transaction results returned by the normal tools may still be presented for any selected card.

## Optional formatter

`scripts/format_transactions.py` accepts JSON on stdin and emits JSON on stdout. It deterministically filters by exact card type, sorts dates descending, counts, and renders a markdown report.

Input schema:

```json
{
  "card_type": "requested exact card type",
  "accounts": [{"card_type": "...", "current_balance": "$0.00"}],
  "transactions": [{"credit_card_type": "...", "merchant_name": "...", "transaction_amount": "$0.00", "transaction_date": "MM/DD/YYYY", "category": "...", "status": "..."}],
  "max_items": 25
}
```

`max_items` is optional and defaults to 25. Output is a JSON object containing `card_type`, `current_balance`, `matched_count`, `shown_count`, `truncated`, `transactions`, and `markdown`. Supply structured records transcribed from normal tool results; never embed customer records in this package.

Example runtime call:

```sh
python3 scripts/format_transactions.py <<'JSON'
{"card_type":"Example Card","accounts":[],"transactions":[]}
JSON
```

Before sending a report, verify that each displayed row belongs to the requested card, dates are newest first, and displayed counts agree with the rows. Before escalating, verify that the customer has explicitly reported unauthorized activity and that the transfer summary names only records actually returned by the lookup.

## Bronze Rewards monthly-report requests

This section applies only when the customer selected **Bronze Rewards Card**, because that is the only product for which the supplied documentation establishes these self-service features.

- For a request for a month-to-date merchant or category summary, first obtain the transactions and ask for the month if it is not clear. Use only matching-card records in that period. Clearly identify any arithmetic as a summary calculated from returned records, rather than claiming access to a separate statement summary.
- The documented self-service route is: sign in, open **Reports** or **Statements**, select the current or prior statement month, then filter by date range, merchant, or amount. The customer may download the selected monthly activity as CSV or PDF. Do not say an export was created unless it actually was.
- The documentation says customers can add notes or tags for reconciliation, but no declared normal banking tool in this Skill performs that change. Do not simulate adding a note/tag; explain that limitation if asked.
- For a transaction the customer believes is missing, explain that the documentation says report items appear once posted. Review returned statuses and distinguish a returned pending status from a completed one. There is no separate pending-activity lookup among the declared tools, so do not claim that pending activity was checked when it was not.
- Weekly reconciliation, consistent tags, and secure storage of exports are documented best practices. Offer them as optional advice only, not as work already performed.
