---
name: debit-card-dispute-human-handoff
description: Prepare and perform a safe human-agent transfer when a customer requests help with one or more debit-card transaction disputes, especially when fraud, a lost card, ATM discrepancy, or recurring charge after cancellation is involved. Use when the available information is incomplete or the customer explicitly requests a human agent.
---

# Debit-card dispute human handoff

## Purpose

Use this Skill to make a concise, accurate handoff rather than filing disputes when a human transfer is appropriate. It preserves known transaction details, identifies missing information, and selects the highest-priority transfer reason.

A transfer does **not** itself file a dispute, freeze a card, replace a card, or block recurring payments. Do not claim that any of those actions occurred unless their respective banking tools were actually called.

## Required inputs

Collect only information the customer has supplied or that was returned by permitted tools:

- Whether the customer explicitly requested a human agent.
- Any fraud/security facts, including lost/stolen card, unauthorized activity, or suspected compromise.
- For each reported issue: card/account identifier or last four digits, merchant/ATM, date, amount, issue description, and known transaction channel.
- For ATM matters: withdrawal/deposit, requested and dispensed/credited amounts, and bank-owned versus third-party ATM when known.
- For a recurring charge: whether and when the merchant was cancelled/contacted and the merchant response.
- Information that remains missing, including any claimed transactions for which details were not provided.

Do not use account/profile lookup results as proof of identity. If filing or account action will be performed, obtain the required identity verification separately and log it according to the available verification procedure.

## Method

1. **Recognize an immediate security handoff.** If any reported issue involves suspected fraud, unauthorized use, a lost/stolen card, identity theft, or another security concern, select `fraud_or_security_concern`. This Tier 1 reason outranks a billing-dispute reason and a generic request for a human.
2. If no Tier 1 condition applies, choose the highest applicable transfer reason using the supplied reason-code policy. For example, use `complex_billing_dispute` only where the matter is a qualifying billing dispute; use `customer_requests_human_no_specific_reason` only when no more-specific reason applies.
3. Create a factual transfer summary. Separate each reported issue, retain the customer’s stated dates and amounts, and clearly label unknown fields. Mention lost-card timing and suspected unauthorized usage prominently. Do not infer a transaction ID, account ID, card ID, verification status, transaction channel, or a fourth transaction from partial information.
4. State what has and has not been attempted. In particular, distinguish a past recurring-charge dispute from a future recurring-payment block. A recurring block affects all recurring payments on the card and does not cancel subscriptions.
5. Call `transfer_to_human_agents` with the selected reason and summary. The transfer tool is the only mechanism that performs the handoff.
6. Tell the customer that they are being connected to a specialist and that the specialist may need the missing transaction and verification details. Avoid promising a refund, provisional credit, dispute approval, or card action.

## Debit-dispute context for the handoff

If the human agent will file a debit-card dispute, preserve these known prerequisites and questions rather than fabricating answers: verified customer, transaction ID, linked open checking account, debit-card ID, amount at least $1, transaction age within 60 days, account-tier open-dispute limit, discovery date, transaction type, card possession, PIN compromise status, merchant-contact status for non-fraud disputes, police-report status for fraud above $500, written-statement consent, and provisional-credit eligibility.

For unauthorized activity where fraud is suspected, classification depends on channel: physical/in-person activity maps to `card_present_fraud`; online/phone activity maps to `card_not_present_fraud`. A charge after cancellation is a past-charge dispute category of `recurring_charge_after_cancellation`; future protection, if requested, is a separate recurring-block process. An ATM withdrawal that dispenses less than requested is an `atm_cash_discrepancy`.

## Optional deterministic summary helper

`scripts/build_handoff.py` creates a reviewable handoff payload from structured facts. It does not call banking tools or make account changes.

Input JSON schema:

```json
{
  "customer_requested_human": true,
  "customer_reference": "optional non-sensitive display reference",
  "security_concern": true,
  "security_notes": ["optional factual security note"],
  "issues": [
    {
      "card_reference": "optional last-four/account label",
      "merchant_or_atm": "optional",
      "date": "optional MM/DD/YYYY or stated date",
      "amount": 0,
      "issue_type": "unauthorized|recurring_after_cancellation|atm_cash_discrepancy|other",
      "details": "optional factual detail",
      "channel": "in_person|online_phone|recurring|atm_withdrawal|atm_deposit|unknown",
      "known_missing": ["optional missing field"]
    }
  ],
  "unresolved_items": ["optional missing claimed issue or question"],
  "attempts": ["optional factual action already taken"]
}
```

The script emits JSON with `reason`, `summary`, `missing_information`, and `review_warnings`. Review the output against the conversation before calling the transfer tool. A `fraud_or_security_concern` result must be used whenever `security_concern` is true or an issue is explicitly classified as unauthorized.

Example runnable invocation in a supported runtime:

```sh
python scripts/build_handoff.py <<'JSON'
{"customer_requested_human":true,"security_concern":false,"issues":[],"unresolved_items":["Transaction details still needed"]}
JSON
```

Validation: confirm the output has a nonempty `summary`, the `reason` is an allowed transfer enum, every reported issue is represented, and all absent facts remain listed as missing rather than guessed.
