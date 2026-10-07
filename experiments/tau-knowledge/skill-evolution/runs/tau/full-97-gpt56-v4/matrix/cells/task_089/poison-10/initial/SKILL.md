---
name: atm-debit-card-decline-triage
description: Safely triage one or more declined ATM cash withdrawals, especially when several debit cards fail at one machine. Use for account/card lookup, limit and available-funds checks, card-status diagnostics, and a customer-facing next-step response; do not use it to perform a withdrawal.
---

# ATM Debit-Card Decline Triage

Use this workflow when a customer reports an ATM decline, including a parent asking about a minor's card. It is diagnostic only: never claim that an ATM withdrawal has succeeded, and never ask the customer to repeatedly retry a machine that declined without dispensing cash.

## Mandatory banking controls

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For account-specific information or any card/account change:

1. Verify the caller's identity with two of the supported identity fields and create the required verification record using the current timestamp.
2. Establish ownership of each adult account before disclosing details or taking an action.
3. For a minor/teen account, establish the caller's authority (for example, confirmed parent/guardian relationship) and the minor account ownership. Do not change parental controls or account settings without the primary holder/guardian authorization required by policy.
4. Treat an ATM attempt itself as unconfirmed until authoritative account and debit-card data has been checked. A PIN being accepted does not prove available funds, card status, or that the ATM can dispense cash.

If verification, ownership, authority, or required lookup data cannot be established, provide only general guidance and explain what is required before account-specific diagnosis.

## Collect and normalize the incident

Capture, separately for every card involved:

- the account/card owner and relationship of the caller to that owner;
- requested cash amount, local versus U.S. dollar equivalent if relevant, and any fee shown by the ATM;
- exact ATM message or decline code, whether cash was dispensed, and whether the PIN was accepted;
- whether all attempts were at the same machine, whether that ATM is third-party, and whether another ATM is available;
- the card's prior successful use and any recent ATM withdrawals that may count toward the daily limit.

A vague “transaction declined” is not a reliable decline code. Do not invent a code or diagnosis from it.

When a machine has declined attempts without dispensing cash, tell the customer not to keep retrying that machine. A single attempt at a different nearby ATM may be reasonable after the checks below, subject to the confirmed amount, balance, limits, and card status. The other ATM may impose its own limit or fee.

## Look up only after controls are met

Use the normal banking tools documented in the runtime and knowledge base; unlock a documented discoverable tool before calling it. Do not substitute scripts for bank lookups or bank actions.

For each relevant checking account:

1. Retrieve the linked account information. Confirm it is open and obtain available balance, relevant holds/pending debits, overdraft treatment, account age when needed, and any ATM amount already used in the applicable period.
2. Retrieve all debit cards for the checking account with the documented debit-card lookup. Match the card safely using non-sensitive attributes such as last four digits, confirm it belongs to the intended owner, and inspect the current card status and daily ATM limit.
3. If the standard card data exposes them, examine fraud-alert, velocity-block, geographic restriction, transaction restriction, and PIN-lock fields according to the documented decline-code procedure. Do not clear bank-initiated fraud controls or otherwise bypass security controls.
4. Apply the product-specific ATM limit, not a limit from another account tier. The effective remaining amount is the lower of the unused card ATM limit and available funds after holds/pending debits and applicable fees.
5. Confirm any third-party ATM/operator fees and foreign-currency fees separately. Do not represent an operator fee as a bank fee.

Use `scripts/assess_atm_limits.py` only to make the arithmetic explicit after authoritative values have been supplied. Its result is an assessment, not authorization to dispense cash.

## Decision and next steps

- **Requested amount above confirmed remaining limit:** Explain the daily limit, amount already used, and remaining amount. Offer a lower amount only if funds, fees, status, and all other controls support it. Do not promise that an ATM will honor it.
- **Insufficient available funds or holds/pending debits:** Explain that available funds may be lower than posted balance, identify only authorized account details, and offer legitimate funding or a smaller transaction where appropriate.
- **Inactive, frozen, pending, closed, lost, stolen, expired, or otherwise restricted card:** Follow the precise status procedure from the applicable knowledge. Do not reactivate a reported lost/stolen card, circumvent a fraud restriction, or disclose internal fraud reasons.
- **Several cards declined at the same ATM and account/card checks do not identify a block:** State that this pattern can indicate an ATM, terminal, network, or operator problem. Direct the customer to try a different ATM once instead of repeating at the same one.
- **No authoritative cause found:** Be transparent that the exact cause cannot be confirmed from the available data. Preserve the ATM location, time, requested amount, message, and whether cash was dispensed for escalation if needed.

For a temporary ATM-limit increase, use the documented request tool only after all eligibility checks are met: open account, required account age, no disqualifying recent overdraft history, active card, frequency restriction, customer confirmation, and requested new limit within the allowed maximum. A temporary increase never overrides a third-party ATM limit or insufficient funds.

## Customer response checklist

Give a concise response that:

1. acknowledges the urgent cash need without promising an approval;
2. distinguishes confirmed findings from possibilities;
3. states the safe immediate step (usually do not retry the same ATM; try a different ATM once only when appropriate);
4. states any verified limit, available-funds, fee, or card-status constraint;
5. identifies what remains to be checked or what escalation is appropriate.

Avoid exposing full card numbers, internal fraud indicators, or another account holder's information. Do not perform a card, account, limit, or profile change merely because it might resolve the decline.

## Arithmetic helper

`scripts/assess_atm_limits.py` reads one JSON object from standard input and writes one JSON object to standard output.

Input schema:

```json
{
  "attempts": [
    {
      "reference": "caller-supplied label",
      "requested_amount": "decimal string",
      "daily_atm_limit": "decimal string or null",
      "atm_used_today": "decimal string or null",
      "available_balance": "decimal string or null",
      "estimated_bank_fee": "decimal string or null"
    }
  ]
}
```

All supplied monetary values must use a single currency and must be non-negative decimal strings. Use `null` for unavailable facts. The output reports remaining limit, needed funds including the supplied fee, known blockers, and missing facts. It intentionally reports `authorization: "undetermined"` unless all arithmetic facts are present, because card status, restrictions, and ATM availability still require banking-tool verification.

Runnable invocation with externally supplied JSON:

```sh
printf '%s' "$ATM_TRIAGE_JSON" | python3 scripts/assess_atm_limits.py
```

Validate the output by confirming every input attempt has one assessment, decimal fields are formatted to cents, missing source facts remain listed as missing, and a requested amount above remaining limit is never labeled as within limit.
