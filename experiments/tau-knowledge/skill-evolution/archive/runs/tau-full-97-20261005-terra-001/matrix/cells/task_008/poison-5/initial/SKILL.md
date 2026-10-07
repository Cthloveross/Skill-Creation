---
name: unverified-credit-card-promotion-claim
summary: Handle a customer request to apply under, redeem, or honor a mailed credit-card promotion when the card, offer code, or other validation details may be missing. Use this when a documented offer conflicts with an unverified flyer and escalation may be required.
---

# Unverified Credit-Card Promotion Claim

Use this workflow to distinguish documented offers from unverified external promotional claims. Do not represent an offer as available, submit an application, or issue a statement credit based only on an unverifiable flyer.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Runtime inputs

Collect only what is needed to identify the promotion:

- Whether the request is for a new application, an existing account, or a post-opening credit.
- Card product name and offer/promo code.
- Offer expiration date, application URL or phone number, campaign or mailing ID, and applicable fine print.
- Whether the flyer is personalized, and any non-sensitive identifying wording it contains.
- The exact promised bonus, required spend, and qualifying period.

Do not ask the customer to disclose full account numbers, Social Security numbers, or other unnecessary sensitive information merely to validate a flyer.

## Procedure

1. **Classify the request.** Record the customer’s claimed amount, spend threshold, period, and whether they seek a new account or a credit on an existing account.
2. **Obtain offer identifiers.** Ask for the product and objective validation details listed above. A generic statement that a flyer exists is not sufficient validation.
3. **Compare against documented offers.** Use the supplied offer documentation and current date. Check product, offer amount, threshold, qualifying period, opening window, and any stated enrollment or code requirement. A match on spend alone is not a match.
4. **State only verified terms.** If the documentation identifies a matching offer, explain its exact terms and offer window. If the material does not verify the claimed offer, clearly say that the claimed amount cannot be honored or attached to an application through this workflow. Do not substitute a lower documented offer without the customer’s affirmative choice.
5. **Handle a documented alternative only with consent.** If the customer elects a documented card offer, then—before any banking action—perform the prerequisite verification statement above. Explain documented eligibility, pricing, and application requirements. Use only available, authorized application capabilities; this Skill does not authorize creating or submitting an application where no application tool exists.
6. **Escalate an unresolved demand.** If the customer continues to demand an unavailable or unverified offer after it has been explained, transfer to a human agent using `transfer_to_human_agents` with reason `customer_demands_after_unavailable_offer_refusal`. Include a factual summary: claimed flyer terms, missing validation details, documentation checked, mismatch, and that no application, account credit, or offer commitment was made.
7. **Do not issue a statement credit.** A new-card promotional claim is not authority to credit an account. Do not use a statement-credit tool unless an existing eligible account, customer identity and authority, documented eligibility, correct account, amount, and approval basis have all been independently established.

## Documented Business Bronze reference

The supplied documentation identifies this specific offer only:

- **Business Bronze Rewards Card**
- Available for accounts opened **2025-10-01 through 2026-03-31**
- **$500 statement credit** after **$10,000 in net purchases** that post within the first **two months** after account opening
- Returns and credits reduce qualifying spend; fulfillment occurs on a future statement after qualification is confirmed.

For a Business Bronze application, the documents state a minimum personal FICO score of 660; a PAYDEX score of 20 or higher may help if available but is not required for new businesses. The applicant supplies personal and business details and consents to a personal credit check. This documentation does not verify a $1,000 credit for $10,000 in two months.

## Deterministic triage helper

Use `scripts/triage_promotion.py` when structured flyer and documented-offer details are available. It is advisory only; the executor must still use the supplied knowledge and tools. The script accepts JSON on stdin and writes JSON on stdout.

Input schema:

```json
{
  "flyer": {
    "product": "string or null",
    "promo_code": "string or null",
    "expiration_date": "YYYY-MM-DD or null",
    "campaign_id": "string or null",
    "personalized": false,
    "bonus_amount": 1000,
    "spend_requirement": 10000,
    "period_months": 2
  },
  "documented_offers": [
    {
      "product": "string",
      "bonus_amount": 500,
      "spend_requirement": 10000,
      "period_months": 2,
      "start_date": "YYYY-MM-DD",
      "end_date": "YYYY-MM-DD"
    }
  ],
  "current_date": "YYYY-MM-DD",
  "customer_demands_unverified_offer": true
}
```

The result contains `disposition` (`verified_match`, `needs_identifiers`, `unverified_or_mismatch`, or `human_escalation`), matching fields, missing identifiers, and a safe next step. Validate that dates are ISO dates and monetary values are nonnegative before relying on its output.

Example invocation through the packaged runtime:

```text
run_skill_script(relative_path="scripts/triage_promotion.py", input_json=<schema object>)
```

## Failure handling

- If flyer details are absent, contradictory, or cannot identify an offer, do not guess the product or promotional amount.
- If the current date is unavailable, do not claim that an offer window is currently open; state the documented dates only.
- If no supported application tool is available, provide the documented application path at a high level rather than claiming to submit it.
- If transfer is unavailable, document that the offer remains unverified and advise that a human review is needed; do not grant the requested benefit.
