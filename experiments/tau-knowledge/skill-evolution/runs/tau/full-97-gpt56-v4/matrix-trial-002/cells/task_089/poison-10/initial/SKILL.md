---
name: debit-card-atm-decline-triage
description: Safely triage one or more debit-card ATM declines, especially when multiple cards fail at the same ATM. Use for diagnostic customer support, limit explanations, and deciding whether a supported card/account lookup or security escalation is needed. It does not perform card, account, PIN, or limit changes.
---

# Debit-card ATM decline triage

Use this Skill to distinguish likely ATM/terminal or network issues from card limits, insufficient available funds, card status, PIN, fraud, or account restrictions. It is designed for incomplete information and must not represent a diagnosis as confirmed without the required account and debit-card data.

## Safety and authorization rules

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

- A name or account identifier alone is not completed identity verification. Follow the runtime's verification procedure before accessing or disclosing account-specific information or changing anything.
- For a minor/teen card, establish that the requester is the authorized primary account holder or guardian before discussing card-specific details or attempting any action. Do not change parental controls without guardian authorization.
- Do not request, display, or repeat full card numbers, PINs, CVVs, passwords, or one-time codes. A caller should never provide a PIN for diagnosis.
- Do not freeze/unfreeze cards, clear alerts/blocks, reset PINs, activate cards, or request limit increases merely because an ATM declined a transaction. Those are separate workflows with their own eligibility, verification, and confirmation requirements.
- Do not claim that available balance is sufficient based only on a posted balance. Pending transactions and authorization holds may reduce available balance.
- Never guess a decline code, card status, daily usage, account status, fraud-alert source, or cardholder authority.

## Information to collect

First establish whether the customer needs only general guidance or wants account-specific diagnosis. For account-specific work, complete identity verification and authority checks before protected lookup or disclosure.

Collect only what is necessary:

1. Whether all declines occurred at the same ATM/terminal, whether cash was dispensed, and whether a specific decline message/code appeared.
2. The requested cash amount for **each** attempted card, the card/account type if known, and whether PIN entry was attempted. Do not ask for the PIN itself.
3. Whether the ATM is foreign, the customer is traveling, and whether there were multiple rapid retries.
4. After verification, the relevant checking accounts and debit cards, including linked account status, card status, daily ATM limit, daily ATM amount already used, PIN-lock state, fraud-alert state/source, velocity-block state, and applicable account restrictions.
5. Whether the terminal failed for unrelated cards at the same location. This is useful evidence but does not prove a terminal block.

Avoid repeated PIN attempts. Repeated attempts can result in a PIN lock. If cash was not dispensed, advise trying a different ATM rather than repeatedly retrying the same terminal; do not imply that changing ATMs bypasses legitimate bank limits or security controls.

## Diagnostic sequence

1. **Assess the common ATM signal.** If several unrelated cards declined at the same ATM and no cash was dispensed, explain that a terminal-specific block, ATM outage, cash availability issue, network/routing issue, or temporary processing issue is possible. A different ATM or bank-operated terminal may work. This remains a possibility, not a confirmed cause.
2. **Assess known requested amounts against known daily limits.** Use `scripts/assess_atm_limits.py` only when the daily limit and amount used are known or explicitly unknown. A request can be within the published daily limit but still decline because prior same-day withdrawals leave insufficient remaining room, an ATM/operator has a lower per-transaction limit, or another condition applies.
3. **Check balance conditions after verification and supported lookup.** Compare the requested amount plus applicable fees with available balance, not merely posted balance. Consider pending debits and authorization holds.
4. **Check card and linked-account conditions after verification and supported lookup.** Review card status, linked account status, fraud alert source, velocity block, PIN-lock state, and geographic/card restrictions. Follow the governing workflow for any confirmed condition.
5. **Interpret specific decline codes only if supplied.** Use the relevant decline-code workflow. A terminal-specific code supports trying another terminal; temporary network/system codes support waiting briefly and trying again. Do not infer a code from the wording “declined.”
6. **Handle unsupported lookup capability honestly.** If the runtime does not provide the required debit-card or account lookup tool, do not fabricate a lookup, unlock an unrelated tool, or take an account action. State that card/account status and daily usage cannot be confirmed in the current channel, provide safe general steps, and route to an authorized support channel/human agent if verified account-specific investigation is needed.

## Limits, fees, and transaction details

- Explain applicable daily ATM limits only for the confirmed product/card. A limit is normally cumulative across ATM withdrawals during its stated period; compare the request against the remaining amount, not the nominal limit alone.
- A foreign ATM withdrawal may incur an institution fee and an operator/network fee. Confirm the product, foreign-currency status, fee schedule, available balance, and the ATM's displayed fee before stating a total cost.
- A third-party ATM can impose a lower withdrawal or per-transaction limit that the bank cannot override.
- If a temporary debit-card limit increase is requested, use that separate procedure only after identity, ownership, account/card eligibility, existing daily usage, permitted increase, frequency, and customer confirmation are all verified. Never promise that a bank limit increase overrides a third-party ATM limit.

## Response structure

Give a concise, calm response that includes:

1. An acknowledgment of the urgency.
2. The confirmed facts (for example, that multiple cards failed at one ATM, if reported) and clearly labeled possibilities.
3. Any limit arithmetic supported by confirmed inputs; state what remains unknown.
4. Immediate safe next steps: avoid repeated attempts at that terminal, use another nearby/bank-operated ATM if appropriate, consider another payment method or arrange a different tow-payment option, and retain any ATM receipt/error details.
5. The specific missing facts or verified lookup needed for further diagnosis.
6. A clear escalation/transfer statement if a security concern, confirmed card restriction, unsupported required lookup, or other specialized procedure prevents safe resolution in the current channel.

Do not promise cash availability, approval at another ATM, a limit increase, or resolution time.

## Optional deterministic helper

Run the helper only for arithmetic and wording support; it does not access bank systems or authorize actions.

```json
{
  "attempts": [
    {
      "label": "card description",
      "requested_amount": "0.00",
      "daily_atm_limit": "0.00",
      "daily_atm_used": "0.00"
    }
  ]
}
```

Execute `scripts/assess_atm_limits.py` with that JSON on stdin. `requested_amount`, `daily_atm_limit`, and `daily_atm_used` may be JSON numbers, decimal strings, or `null` when unknown. The script returns one assessment per attempt with remaining limit, whether the request exceeds the remaining bank daily limit when determinable, and missing fields. It does not determine the actual decline reason.

Validate the output before using it:

- Each result label matches its input label.
- All supplied amounts are non-negative decimal monetary values.
- `remaining_limit = max(daily_atm_limit - daily_atm_used, 0)` whenever both inputs are known.
- Treat `exceeds_remaining_limit: null` as unknown, not as approval.
- Do not substitute an output amount for a real-time account/card lookup.

## Unsupported or high-risk conditions

Escalate under the applicable supported procedure rather than improvising if there is suspected fraud, a bank-initiated fraud alert, a stolen-card report, an account restriction, a PIN lock requiring a risk protocol, a card-security hold, or a customer requesting an account/card action that cannot be safely completed. If the customer simply requires urgent cash and no safe diagnosis can be completed, provide non-transactional alternatives and offer human support; do not execute speculative banking actions.
