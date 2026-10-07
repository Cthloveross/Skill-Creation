---
name: verify-unidentified-credit-card-promotion
description: Assess a customer-claimed credit-card promotion from a flyer, mailer, email, or similar external communication; verify offer and account prerequisites conservatively, prevent unsupported statement credits, and transfer an unconfirmed claim using the highest applicable policy reason.
---

# Verify an Unidentified Credit-Card Promotion

Use this Skill when a customer asks to redeem, honor, review, or receive a credit-card promotional benefit claimed from a flyer, letter, email, or other external communication, but the offer identity, account, eligibility, or invitation details are not established.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Safety Boundaries

- Treat a customer-provided flyer or description as a claim, not proof that an offer exists or that the customer qualifies.
- Do not open an account, make an application decision, alter offer terms, or apply a statement credit based only on the claimed communication.
- A similarly worded offer does not verify a claim if a material term differs: product, campaign, reward type or amount, spend requirement, qualifying period, offer window, invitation requirement, or eligibility.
- Do not request a full SSN, password, security answer, or other sensitive credential to identify a flyer. Ask only for non-sensitive flyer identifiers: card/product name, campaign code, RSVP or application number, personalized application URL, barcode/QR-code text, offer phone number, or mailing address.
- Never promise that an unverified offer will be honored. State that any promotional credit requires a verified offer, verified eligibility, and an identified eligible card account.

## Information to Establish

Collect only the minimum information needed:

1. The claimed terms: product name, reward type and amount, required spend, qualifying period, and application/offer dates.
2. Non-sensitive offer identifiers listed above.
3. Account state: whether the customer has a profile, a profile email or user ID if applicable, whether a card account exists, and whether identity has been verified.
4. Verified promotion records available to the executor, including their material terms and eligibility conditions.
5. Whether the customer wants explanation, application information, review, or that the claimed benefit be honored.

## Procedure

1. **Separate verification from action.** Tell the customer that the offer must be identified and verified before redemption, application of a statement credit, or any eligibility representation can proceed.
2. **Identify the communication.** If product or campaign details are absent, request the available non-sensitive flyer identifiers. Do not guess a product from a spend amount or reward amount.
3. **Review and compare verified records.** Compare every material term. A partial match, a conflict, an expired window, a missing required invitation, or insufficient data leaves the claim unverified.
4. **Establish account status without invention.** If the customer provides a profile identifier, perform only the permitted profile lookup. If no account is found, say so. If no lookup identifier or conclusive lookup is available, state that **no account/profile status is available**. Do not imply that an account, ownership, or eligibility was found.
5. **Verify identity before account-specific activity.** For an existing customer, confirm two available identity fields and log verification with the current timestamp before accessing account-specific information or taking a banking action. Then verify authority, account ownership, product eligibility, account status, the precise promotion, and qualification.
6. **Handle pre-applicants correctly.** A customer with no profile or eligible card account cannot receive a statement credit. Do not search transactions or start the statement-credit workflow. If a verified offer identifies a product, provide only the published application path and requirements; do not promise approval or a benefit.
7. **State the outcome accurately.** For an unverified or conflicting claim, explain that available information does not confirm the claimed promotion and that no credit can be applied. For a confirmed offer, still require verified invitation, eligibility, account, and qualification before any account action.
8. **Choose the highest applicable transfer reason.**
   - Use `unconfirmed_external_communication` for an initial request to review or transfer an unverified customer-claimed flyer, letter, email, program, or offer after reasonable identifier collection and knowledge review.
   - Use `customer_demands_after_unavailable_offer_refusal` instead when all of the following are true: the customer was informed that the offer is unavailable or cannot be confirmed, persists after those refusals, and expressly demands a human. This is a Tier-1 reason and overrides the Tier-2 unconfirmed-external-communication reason.
   - Do not use the Tier-1 reason merely because a customer makes an initial request for review or a single human-transfer request.
9. **Transfer with a factual summary.** Call `transfer_to_human_agents` using the selected reason. Include claimed terms, identifiers provided or absent, review/mismatch result, known account-status limitation, what was explained, and that no statement credit was applied. Never claim the account is identified, verified, eligible, or credited unless that was actually established.
10. **Close after a successful transfer.** Tell the customer that no statement credit has been applied and that the matter was forwarded to a human agent for review. Do not imply that a transfer approves, honors, or guarantees the claimed offer.

## Transfer Summary Templates

For an initial unverified external communication:

`Customer requests review of a claimed external credit-card promotion: [claimed terms]. Provided identifiers: [identifiers or none]. Available promotion records were reviewed; the claim is [unverified or materially inconsistent: fields]. [No account/profile status is available / No account was located / Customer reports no profile or eligible card account.] No statement credit was applied. Customer requests review.`

For a repeated unavailable-offer refusal followed by an explicit human demand, use the Tier-1 reason and add the persistence history:

`Customer persists after being informed that the claimed external promotion could not be verified or is unavailable and expressly requests a human. Claimed terms: [terms]. Identifiers: [identifiers or none]. Review result: [unverified or mismatch]. [accurate account-status sentence]. No statement credit was applied.`

Use only an account-status sentence supported at transfer time. If a later clarification establishes that the customer is a pre-applicant, record it then; do not retroactively say it was known at an earlier handoff.

## Statement-Credit Guardrail

Only a verified, qualified case may enter the documented statement-credit workflow. Before that workflow, complete all mandatory controls and confirm an identified user, eligible credit-card account ID, positive exact amount, permitted reason, offer eligibility, and qualification. For an earned promotion, use the documented `promotional_credit` reason. Unlock the documented tool before use and verify the resulting negative transaction and statement-balance reduction.

Never invoke or unlock a statement-credit tool for an unidentified customer, a pre-applicant, an unverified flyer, or an offer whose eligibility is not confirmed.

## Deterministic Assessment Helper

`scripts/assess_external_promo.py` is an advisory classifier. It reads one JSON object from stdin and writes one JSON object to stdout. It does not search knowledge, verify identity, perform a banking action, or call transfer tools.

Run it with executor-supplied data:

```sh
python3 scripts/assess_external_promo.py < supplied-input.json
```

Input schema:

```json
{
  "claim": {
    "channel": "flyer|email|letter|other",
    "product": "string or null",
    "campaign_code": "string or null",
    "personalized_identifier": "string or null",
    "reward_type": "statement_credit or other string or null",
    "reward_amount": "number or null",
    "spend_amount": "number or null",
    "period_months": "number or null"
  },
  "customer": {
    "has_profile": "boolean or null",
    "user_id": "string or null",
    "account_id": "string or null",
    "identity_verified": "boolean"
  },
  "candidate_offers": [
    {
      "product": "string or null",
      "campaign_code": "string or null",
      "reward_type": "string or null",
      "reward_amount": "number or null",
      "spend_amount": "number or null",
      "period_months": "number or null",
      "offer_start": "YYYY-MM-DD or null",
      "offer_end": "YYYY-MM-DD or null",
      "requires_invitation": "boolean"
    }
  ],
  "as_of": "YYYY-MM-DD or null",
  "customer_requests_honor_or_review": "boolean",
  "persisted_after_unavailable_offer_refusal": "boolean",
  "explicit_human_transfer_demand": "boolean"
}
```

The output includes `ok`, `claim_verification`, `account_action`, `account_status`, `missing_identifiers`, `candidate_match_indexes`, `next_steps`, and an optional `transfer` recommendation. A recommended transfer is not an action: the executor must confirm the observed conversation facts and use the actual transfer tool. In particular, a Tier-1 recommendation requires both supplied persistence-after-refusal and explicit-human-demand facts.

## Failure Handling

- If promotion data is unavailable, incomplete, conflicting, or ambiguous, classify the claim as unverified; do not fill gaps from the customer’s statement.
- If a profile lookup finds no record, do not guess alternate identifiers or access card information.
- If identity verification, account details, eligibility, or a required tool prerequisite is unavailable, take no banking action.
- Escalate an unverified external claim only when review or transfer is sought, using the highest applicable reason tier. Otherwise explain the missing verification requirement and request the minimum non-sensitive information needed.
