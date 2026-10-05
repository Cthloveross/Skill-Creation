---
name: verify-unidentified-credit-card-promotion
description: Assess a customer-claimed credit-card promotion from a flyer, mailer, email, or similar external communication; safely determine whether it can be verified, avoid unsupported statement-credit actions, and route an unconfirmed claim for human review when appropriate.
---

# Verify an Unidentified Credit-Card Promotion

Use this Skill when a customer wants to redeem, honor, or receive a benefit from a claimed credit-card offer but the offer identity, campaign code, invitation details, account, or eligibility cannot yet be established. It is especially applicable to mailed flyers whose terms do not match verified product promotions.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Boundaries

- Treat a flyer, email, or customer description as an external claim, not as proof that an offer exists or that the customer is eligible.
- Do not alter an offer, open an account, make an application decision, or apply a statement credit based solely on a claimed promotion.
- A statement credit can be applied only after there is an identified, eligible card account and all mandatory controls have been completed. A pre-applicant with no profile or card account cannot receive a statement credit.
- A similarly worded promotion is not a verification if a material term differs, including product, reward amount, spending requirement, qualifying period, offer window, invitation requirement, or customer eligibility.
- Do not request sensitive credentials or a full SSN to identify a flyer. Request only non-sensitive offer identifiers such as the named card product, campaign/RSVP/application number, personalized URL, phone number, barcode/QR-code text, or mailing address.

## Inputs to Gather

Capture only what is necessary:

1. Claimed terms: product/card name, reward type and amount, spend threshold, qualification period, and offer/application dates.
2. Offer identifiers: campaign code, RSVP or application number, personalized URL, barcode/QR-code text, contact phone, or mailing address.
3. Customer/account state: whether the customer has a profile, a user ID or profile email if one exists, whether an eligible card account exists, and whether identity has been verified.
4. Verified promotion records: all matching product/campaign terms and eligibility conditions available in the product knowledge supplied to the executor.
5. Whether the customer is asking for an explanation, wants an application, or asks that the claimed benefit be honored or reviewed.

## Procedure

1. **Separate lookup from action.** Explain that you will first verify the claimed offer. Do not imply that an application, account opening, or credit will occur.
2. **Identify the offer.** Ask for the non-sensitive identifiers above if product or campaign information is missing. If the customer cannot provide an identifier, record the offer as unverified rather than guessing a product.
3. **Compare all material terms.** Review available, verified promotion information. Compare product, incentive type and amount, spending threshold, qualifying period, offer window, new-customer/invitation conditions, and fulfillment rules. A partial match or any conflict is not a confirmed offer.
4. **Check account prerequisites before any account action.** If the customer says they already have an account, locate the profile through an available identifier and verify identity by confirming two of the available identity fields. Log verification with the current timestamp only after those fields are confirmed. Then confirm authority, card-account ownership, product eligibility, account status, and the exact promotion before accessing account details or taking action.
5. **Handle pre-applicants correctly.** If there is no profile or card account, do not look for transactions or invoke a statement-credit process. Explain that a statement credit is an account benefit that can only be considered after an account exists and verified promotional qualifications have been met. If a verified offer identifies a product, provide only the applicable published application path and terms; do not promise approval or a benefit.
6. **Resolve the outcome.**
   - **Confirmed offer and qualified account:** follow the applicable account-credit procedure only after all mandatory controls, including confirmation of the precise amount, account, and reason, are complete.
   - **Confirmed offer but no account/application:** describe the verified offer and normal application/qualification requirements; do not manually grant the benefit.
   - **Unverified or conflicting claim:** clearly state that the claimed offer cannot be confirmed from the available information and cannot be honored or credited by the agent.
7. **Escalate the unverified external claim when review is sought.** If a customer persists in asking that an unverified flyer be honored, or asks for review/transfer after reasonable identifier collection and knowledge review, call `transfer_to_human_agents` with reason `unconfirmed_external_communication`. Include a factual summary: identifiers provided or absent, that available promotions were reviewed, material mismatch or inability to verify, account/profile status, and the requested resolution. Do not claim that a credit was approved.

## Statement-Credit Guardrail

If a verified case reaches a credit action, use the documented statement-credit tool workflow only after all prerequisite checks. Its required inputs are an identified user, an eligible credit-card account ID, a positive amount, and an allowed reason. For an earned card promotion, the reason must be `promotional_credit`. Unlock the discoverable tool before calling it and confirm the resulting negative transaction and statement-balance reduction. Never use that workflow for an unidentified pre-applicant or to compensate for an unverified flyer.

## Transfer Summary Template

Use a concise, non-speculative summary such as:

`Customer requests review of a claimed external credit-card promotion. The customer provided [identifiers or “no product/campaign/personalized identifier”]. Available promotion records were reviewed; the claim is [unverified / materially inconsistent on: fields]. Customer [has no profile or eligible card account / has verified account status: ...]. No statement credit was applied. Customer requests that the claimed benefit be honored or reviewed.`

## Optional Deterministic Assessment Helper

`scripts/assess_external_promo.py` converts supplied claim, account, and candidate-offer data into a conservative classification. It does not access customer systems, verify identity, search knowledge, perform banking actions, or call transfer tools.

Run it with a valid JSON file supplied by the executor:

```sh
python3 scripts/assess_external_promo.py < input.json
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
    "has_profile": "boolean",
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
  "customer_requests_honor_or_review": "boolean"
}
```

The script emits JSON with `ok`, `claim_verification`, `account_action`, `missing_identifiers`, `candidate_match_indexes`, `next_steps`, and an optional `transfer` object. Validate that `ok` is `true`; then use the result as a decision aid alongside actual knowledge review and mandatory controls. A `verified_candidate` result still requires invitation/eligibility and account verification before any action.

## Failure Handling

- If the candidate promotion data is unavailable or incomplete, state that the claim cannot be verified; do not fill in missing terms from the customer’s statement.
- If profile lookup does not find a customer, do not repeatedly search using guesses and do not access card information.
- If identity cannot be verified, stop before account-specific actions and do not log a successful verification.
- If tool access, account data, or a required prerequisite is unavailable, take no banking action. Escalate only when the request is for review of an unverified external communication; otherwise explain the missing requirement and request the minimum necessary information.
