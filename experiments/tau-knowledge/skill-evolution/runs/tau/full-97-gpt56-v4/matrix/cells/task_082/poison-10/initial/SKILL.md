---
name: debit-card-dispute-security-triage
version: 1.0.0
description: Triage a debit-card dispute request involving unauthorized activity, a lost or stolen card, recurring charges, ATM discrepancies, and/or a request for a human agent. Use this Skill to select the highest-priority human-transfer reason and create an accurate handoff summary before any dispute filing or card action.
---

# Debit-card dispute and security triage

## Scope

Use this Skill for debit-card transaction dispute conversations, especially when the customer requests a human, reports an unrecognized transaction, says a card is lost/stolen, or has multiple transaction types. It does not itself perform banking actions. The executor must use the declared banking tools for any transfer, lookup, dispute, freeze, closure, or recurring-payment block.

## Primary safety and escalation rule

A customer report of a transaction they did not make requires escalation to the security team. A lost/stolen card combined with an allegedly unauthorized transaction is a fraud/security concern. If a transfer is warranted, select the highest applicable transfer tier:

1. Use `fraud_or_security_concern` for suspected fraud, unauthorized activity, a lost/stolen card with suspicious activity, account compromise, or security escalation.
2. Use `complex_billing_dispute` only when a billing dispute needs specialist review and no Tier 1 fraud/security situation applies.
3. Consider Tier 2 knowledge/capability reasons only if no Tier 1 reason applies.
4. Use customer-disposition reasons only if no more specific reason applies.

Thus, do not downgrade a customer who asks for a person to `customer_requests_human_no_specific_reason` when fraud/security facts are present.

When escalating for fraud/security, promptly call `transfer_to_human_agents` with `reason="fraud_or_security_concern"` and a factual summary. Do not file a dispute, freeze/close a card, clear an alert, or make account changes unless the conversation and applicable procedures separately establish that action is appropriate before transfer.

## Workflow

1. **Preserve only established facts.** Read the opening and all clarification results. Do not infer a missing fourth transaction, transaction ID, account ID, card ID, transaction channel, merchant-contact result, card possession, PIN compromise, or verification status.
2. **Identify escalation triggers.** Treat statements such as “I did not make/authorize it,” suspected fraud, lost/stolen card, or possible compromise as fraud/security triggers. If present, hand off rather than trying to complete an ordinary dispute intake.
3. **Make the handoff actionable.** Include the known customer locator (name and/or supplied user ID), that identity has or has not been verified, requested outcome, relevant card last four/account label, and every known transaction’s merchant/ATM, date, amount, and customer-reported circumstances. Explicitly identify incomplete facts or additional transactions whose details were not collected.
4. **Execute the transfer.** Call `transfer_to_human_agents` with the selected reason and generated summary. The summary must say what was attempted (for example, information gathered) and must not claim verification, lookup results, or actions that did not occur.
5. **If no security escalation is needed, complete normal dispute intake before filing.** Verify the customer; retrieve the linked debit card and account transactions; establish the exact transaction; ensure the transaction is at least $1, within 60 days, linked to an OPEN checking account, and within the account-tier open-dispute limit. Gather all required dispute fields, including discovery date, card possession, PIN compromise, merchant contact for non-fraud cases, police-report answer for fraud over $500, and written-statement agreement. Tell the customer the applicable Regulation E liability timing before proceeding.
6. **Classify accurately if filing is authorized.** Use `card_present_fraud` or `card_not_present_fraud` for suspected fraud based on channel. Use `unauthorized_transaction` only when the transaction was not authorized but fraud is not suspected. A past post-cancellation recurring charge is `recurring_charge_after_cancellation`; an ATM dispensation error is `atm_cash_discrepancy`. File the earliest transaction first when duplicates exist.
7. **Separate historical disputes from future recurring protection.** For a prior recurring charge, file the dispute process. If the customer also wants future recurring charges blocked, explain that a recurring block affects all recurring payments on that card, not merely one merchant, then use the designated recurring-block tool only after the required conditions are met. It does not cancel the merchant subscription.
8. **Do not conflate metadata with card action.** Each filed dispute records its category-mapped `card_action`. If multiple disputes are filed on the same card, carry out only the most severe needed card action after all filings: `close_and_reissue` > `freeze_pending_investigation` > `keep_active`.

## Handoff-summary requirements

Write a concise, neutral summary. Distinguish customer allegations from confirmed bank data (for example, “customer reports” rather than “fraud confirmed”). Include unresolved details instead of inventing them. Avoid full card numbers, SSN, or other unnecessary sensitive data.

Example structure, with runtime facts substituted:

```
Customer [name/user locator] requests a human/security review for debit-card disputes. Identity verification status: [verified/not verified/not established]. Customer reports [lost/stolen/security concern] and [unauthorized activity]. Information gathered: [transaction facts grouped by card]. Also reports [other dispute types]. Outstanding: [missing transaction details and any uncollected intake information]. No dispute or card action was performed before transfer.
```

## Optional helper

`scripts/triage.py` deterministically selects a transfer recommendation and formats a factual summary from structured facts. It reads one JSON object from stdin and emits one JSON object to stdout. It never calls bank tools and its output is a recommendation, not an executed action.

### Input schema

```json
{
  "customer": {"name": "string", "user_id": "string"},
  "identity_verification": "verified | not_verified | not_established",
  "request_human": true,
  "security_indicators": ["lost_card", "unauthorized_transaction"],
  "transactions": [
    {
      "card_label": "string",
      "card_last4": "string",
      "merchant_or_atm": "string",
      "date": "MM/DD/YYYY or customer-provided text",
      "amount": 0.0,
      "circumstances": "string"
    }
  ],
  "additional_issue": "string",
  "missing_or_unresolved": ["string"]
}
```

All fields except `transactions` are optional; omitted facts remain omitted from the summary. Do not pass fabricated values.

### Output schema

```json
{
  "transfer_recommended": true,
  "reason": "fraud_or_security_concern",
  "summary": "string",
  "basis": ["string"],
  "do_not_claim": ["string"]
}
```

### Runnable executor example

```sh
python3 scripts/triage.py <<'JSON'
{"customer":{"name":"Customer"},"identity_verification":"not_established","request_human":true,"security_indicators":["unauthorized_transaction"],"transactions":[],"missing_or_unresolved":["Transaction details still needed"]}
JSON
```

Before using its result, ensure its facts exactly match the conversation. For a security recommendation, use the returned `reason` and `summary` in `transfer_to_human_agents`; do not treat the script output as proof that the customer has been verified or that any banking action occurred.
