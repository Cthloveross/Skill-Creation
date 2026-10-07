---
name: pin-lock-identity-gate-and-fraud-review
description: Safely handle requests to unlock PIN-locked debit cards. Use this skill to gate all card investigation and unlock activity on successful identity verification, transfer customers who cannot be verified, and complete the required per-card fraud-risk review for verified customers.
---

# PIN-Locked Debit Card Identity Gate and Fraud Review

Use this workflow when a customer requests help with a debit card whose PIN is locked or whose PIN-related decline code indicates a lock. Never unlock a PIN-locked card based only on the customer's request.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## 1. Identify and verify before card activity

1. Use a supplied customer identifier (such as full name or email) only to locate the candidate customer profile.
2. Verify identity by matching at least two of these four customer-provided fields against the located profile: date of birth, email, phone number, and address. Do not read profile values to the caller or confirm which submitted value was wrong.
3. Log verification only after two fields match, using the runtime's verification-record tool and its required timestamp.
4. Before verification, do not retrieve account, card, balance, or transaction details; do not unlock, reset a PIN, clear a security block, or disclose whether a card exists.

Use `scripts/verification_gate.py` to consistently evaluate field matches without placing profile values in its output. It is an advisory helper; the executor remains responsible for using approved runtime tools and for making any transfer.

### If identity cannot be verified

If the caller repeatedly provides nonmatching information, has exhausted available verification opportunities, or otherwise cannot satisfy the two-field verification requirement:

- Stop the PIN-lock investigation. Do not look up cards or transactions and do not take a card action.
- Do not disclose the profile value, the number of matching fields, card status, or fraud-risk calculations.
- Transfer to a human specialist with `transfer_to_human_agents` using reason `account_ownership_dispute`. This is the applicable highest-priority transfer reason for identity-verification failure requiring specialist handling.
- Give a concise, non-sensitive summary such as: `Caller requested assistance with PIN-locked debit card(s), but identity verification could not be completed. No card action was taken; specialist verification is required.`
- Tell the caller only that identity verification could not be completed and that a specialist will assist. Do not accuse the caller of fraud.

A security concern may additionally warrant security-team handling, but an identity-verification failure must not be bypassed by attempting an unlock or PIN reset.

## 2. Verified-customer PIN-lock workflow

Only after verification, retrieve the linked checking account and all debit cards using the supported runtime procedures. Confirm card ownership, ACTIVE status where required, card details, and the requested card(s). If multiple cards are PIN locked, investigate every locked card independently and do not unlock any until all relevant cards have been investigated.

For every PIN-locked card, follow `references/pin_lock_fraud_protocol.md` exactly:

1. Check automatic escalation triggers before scoring.
2. Collect the card and account history needed for every score component. Use only observed facts. Do not treat unavailable data as zero; if required information cannot be established, do not unlock and escalate for review.
3. Calculate the internal score per card. Never reveal calculations, individual scores, or internal fraud labels to the customer.
4. Apply the threshold, single-flag escalation, and customer-question rules in the reference. Recalculate only when the reference explicitly permits a confirmed explanation to remove a flag.
5. Complete the required post-unlock step based on lock frequency, or follow the cannot-unlock procedure.

Use normal banking tools only after all prerequisites are met. This skill does not invent an unlock tool: use only an unlock capability actually provided by the runtime and only when the protocol authorizes an unlock.

## 3. PIN reset alternative

When a PIN reset is the authorized outcome, first confirm that the customer is verified, owns the card, and that the card is ACTIVE. Confirm the card's last four digits and obtain a new four-digit PIN. The PIN must not be sequential, all one digit, the customer's birth year, or birth month/day. Use the supported reset tool with the card ID, last four digits, and new PIN. Never display or repeat a PIN to the customer.

## Script interface and validation

`scripts/verification_gate.py` reads one JSON object from stdin and writes one JSON object to stdout.

Input schema:
- `profile`: object containing `date_of_birth`, `email`, `phone_number`, and `address`. Values may be strings or null.
- `claims`: object containing any of those same fields supplied by the caller.
- `attempts_exhausted`: boolean. Set this only when the conversation establishes that verification cannot be completed; do not invent a fixed retry count.

Output contains only field names and a status, never profile values. `verification_status` is one of `verified`, `additional_identity_field_required`, or `identity_verification_failed`. A failed status includes the mandated transfer reason and a safe summary.

Runnable structural call example (replace the nulls and empty claims with runtime-supplied data during a real case):

```sh
printf '%s\n' '{"profile":{"date_of_birth":null,"email":null,"phone_number":null,"address":null},"claims":{},"attempts_exhausted":false}' | python3 scripts/verification_gate.py
```

Validate the helper result before acting: only `verified` permits the post-verification workflow; `additional_identity_field_required` means obtain another permitted field without exposing records; and `identity_verification_failed` requires the transfer above. Reject malformed input rather than guessing identity facts.
