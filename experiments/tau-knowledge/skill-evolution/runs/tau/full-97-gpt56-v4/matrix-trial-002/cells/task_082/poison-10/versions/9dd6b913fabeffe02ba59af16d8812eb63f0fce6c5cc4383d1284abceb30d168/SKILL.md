---
name: secure-dispute-human-handoff
description: Route a banking customer to a human agent when a request includes unauthorized transactions, a lost/stolen payment card, fraud, security concerns, or several dispute types. Select the highest applicable transfer reason and prepare a factual, actionable handoff summary.
---

# Secure Dispute Human Handoff

Use this Skill when the customer requests a human handoff and their issue includes possible fraud, unauthorized transactions, a lost or stolen card, identity theft, or another security concern. It also applies when multiple dispute types must be summarized for one human-agent transfer.

## Procedure

1. Read the conversation and supplied observations. Extract only customer-provided or tool-confirmed facts:
   - customer name or identifier, if supplied;
   - each affected account/card descriptor (use only a last-four/card nickname if provided);
   - transaction date, amount, merchant or ATM, and the customer’s stated issue;
   - lost-card status and when it was lost/reported;
   - identity-verification status.
2. Do not perform account changes, disputes, card replacements, or transactions merely because a transfer is being made. Do not state that identity was verified unless a completed verification and audit record are actually present.
3. Choose the transfer reason from the governing reason-code policy, using the highest applicable tier. An unauthorized transaction, fraud claim, lost/stolen card, or security concern requires `fraud_or_security_concern`, even if the same handoff also includes an ATM error or a recurring/subscription billing dispute. Do not downgrade this to a general customer-request or billing reason.
4. Build a concise factual summary that lets the human agent locate and investigate every reported item. State the security issue first, then enumerate the remaining disputes. Include identity-verification status and any relevant limitations of the work already performed.
5. Call `transfer_to_human_agents` exactly once with the selected `reason` and the prepared `summary`. Explain to the customer that they are being connected to a human agent. Do not expose sensitive full account data unnecessarily.

## Summary checklist

Before transferring, ensure the summary includes:

- why the handoff is urgent (for example, claimed unauthorized activity and a lost card);
- all reported transactions, each with available date, amount, merchant/ATM, card descriptor, and allegation;
- relevant card-loss/reporting facts;
- whether identity verification has been completed, or that it has not;
- what was and was not attempted before transfer.

Use neutral wording such as “customer states” or “customer reports”; do not characterize an allegation as confirmed fraud. If a field is unavailable, say it was not provided rather than inventing it.

## Optional payload helper

`scripts/build_transfer_payload.py` creates a validated recommendation and a factual summary from structured runtime input. It reads one JSON object from stdin and writes one JSON object to stdout. It does **not** call banking tools or transfer a customer.

Input schema:

```json
{
  "customer": "optional name or identifier",
  "issues": [
    {
      "card": "optional non-sensitive card descriptor",
      "date": "optional date",
      "amount": "optional amount",
      "merchant_or_atm": "optional merchant or ATM",
      "description": "customer-reported issue"
    }
  ],
  "security_concern": true,
  "lost_card_details": "optional customer-reported status",
  "identity_verification_status": "completed, not completed, or unknown",
  "attempted": "optional work performed before handoff",
  "other_applicable_reasons": ["optional valid reason codes"]
}
```

The output contains `reason`, `summary`, `needs_human_transfer`, and `validation_errors`. If `security_concern` is true, the helper recommends `fraud_or_security_concern`. Review the generated summary against the conversation before passing it to `transfer_to_human_agents`.

## Validation

A valid transfer has a supported reason code, a nonempty summary, and no fabricated facts. For a security/fraud case, confirm that the final tool argument is exactly `fraud_or_security_concern` and that the summary preserves all supplied dispute details and verification status.
