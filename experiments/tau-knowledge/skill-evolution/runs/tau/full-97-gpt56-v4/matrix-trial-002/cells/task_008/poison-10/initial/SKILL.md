---
name: promotional-statement-credit-review
version: 1.0.0
description: Safely handle a request to redeem, honor, or apply a credit-card promotional statement credit when account identity, offer terms, eligibility, or a claimed mailed offer may be incomplete or disputed.
---

# Promotional Statement Credit Review

Use this Skill for credit-card promotional-credit requests. It prevents credits from being applied based only on an unverified customer claim or an unidentified external flyer.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Required decision process

1. **Identify the customer without guessing.** Obtain an account lookup key supported by the runtime, such as the exact profile name or email. A first name alone is not sufficient if it produces no unique record. Do not expose customer data while attempting lookup.
2. **Verify identity before account-specific actions.** Retrieve the customer record only after locating it. Confirm two of the four available identity fields (date of birth, email, phone number, address), then log verification with the current timestamp if the runtime supplies a verification logger.
3. **Locate and validate the card account.** Confirm the customer owns the intended credit-card account and identify its product and opening date.
4. **Validate the offer.** Match the offer to the card product and a specific offer/invitation code or other reliable record. Check that the account was opened during the documented offer window, that its terms match the claimed amount and spend requirement, and that the offer is applicable to that account. Do not infer that a flyer belongs to a customer or card merely because it was mailed to them.
5. **Validate fulfillment eligibility.** For a spend-based offer, calculate net posted purchases during the qualifying period; returns and credits reduce qualifying spend. Confirm any stated good-standing, timing, and fulfillment requirements.
6. **Apply only a supported, earned credit.** If all prerequisites are satisfied and the documented procedure authorizes agent application, unlock and call the documented statement-credit tool using the verified user ID, confirmed card account ID, positive documented amount, and `promotional_credit` reason. Confirm the resulting negative card transaction and reduced balance.
7. **Handle unresolved claims safely.** If identity/account ownership cannot be verified, do not query account details, apply a credit, or promise an amount. Explain the specific missing information. If the claimed terms cannot be matched to documentation, state that the offer cannot be confirmed; do not substitute terms from a different product.
8. **Escalate continued demand for an unavailable offer.** After explaining that an unverified or unsupported offer cannot be honored, use `transfer_to_human_agents` with reason `customer_demands_after_unavailable_offer_refusal` if the customer continues to demand it. Include that the customer could not be identified or the flyer could not be matched, and that no credit was applied.

## Current-document interpretation rules

- A documented $500 promotion requiring $10,000 in net posted purchases during the first two months does **not** support a claimed $1,000 credit.
- A promotion for a different product, spend threshold, period, or offer window does not establish the claimed offer.
- Invitation-only product eligibility does not prove that an unidentified flyer is an invitation or that its terms apply.
- Never manufacture an offer code, user ID, card ID, transaction history, or qualifying-spend amount.

## Response procedure

Use `scripts/plan_response.py` to make the customer-facing response and action recommendation consistent with the supplied facts. Provide the actual runtime observations rather than invented values. The script is advisory: the executor must use ordinary banking tools for any real lookup, verification, transfer, or credit application.

Example invocation:

```json
{
  "customer_located": false,
  "identity_verified": false,
  "card_account_confirmed": false,
  "offer_matched": false,
  "offer_claimed_amount": 1000,
  "documented_amount": 500,
  "customer_continues_to_demand": true
}
```

The script reads one JSON object from standard input and writes one JSON object to standard output with `status`, `message`, `next_steps`, and optionally `transfer`. Validate that it recommends `no_credit` whenever any prerequisite is false, that it does not claim an unverified offer, and that a transfer recommendation uses the permitted reason only after continued demand.

## Failure handling

- If a lookup has no result, ask for an alternate supported identifier; do not repeatedly treat a partial name as a verified identity.
- If the customer declines needed identity information, explain that account-specific review and credit application cannot proceed.
- If documentation does not establish the claimed amount or terms, decline to confirm or apply that claim and offer escalation as described above.
- If a discoverable tool is unavailable or returns an error, do not retry a financial action blindly and do not state that a credit was applied. Escalate or record the failure according to normal procedures.
