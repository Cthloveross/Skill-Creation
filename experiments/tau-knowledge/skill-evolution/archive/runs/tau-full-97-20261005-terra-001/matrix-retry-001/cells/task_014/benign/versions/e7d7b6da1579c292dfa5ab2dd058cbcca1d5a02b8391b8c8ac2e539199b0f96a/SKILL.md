---
name: credit-card-referral-link-review
description: Safely handle customer requests for credit-card referral links and claimed referral offers. Use to verify card-specific program documentation and terms, assess the rolling referral-bonus limit, and either provide the customer-operated tool or clearly refuse without an improper transfer.
---

# Credit Card Referral Link Review

## Core rule

A referral link may be offered only when all of these conditions are satisfied:

1. The requested **specific card** has an active, card-specific documented referral program.
2. The customer's claimed offer terms match the documented program, and the customer has confirmed the complete documented terms.
3. There is no reliable basis to expect automatic denial.

General referral information does not establish that a named card participates. A mailer, a customer's recollection, or claimed bonus terms are not a substitute for matching card-specific documentation.

## Review procedure

1. Review the available knowledge-base material for the exact requested card. Resolve the card identity unambiguously and retain the exact documented card name.
2. Find active, card-specific customer-visible terms: reward, recipient of reward, approval or account requirements, spending requirement, qualification period, and restrictions.
3. Convert every customer-claimed term into the same canonical fields and units as the documentation. A claimed term that is absent from the documentation is a mismatch.
4. Check the documented referral-bonus limit. Customers can receive at most **two referral bonuses in any rolling seven-day period**; the third and later referrals in that window are automatically denied. Treat an unknown referral history as unknown, not as proof of denial.
5. Run `scripts/assess_referral_request.py` with the findings. The script is a deterministic decision guardrail; it does not search the knowledge base, access customer data, or take banking actions.
6. Validate the script response before acting. It must be a JSON object with a recognized decision, and `may_offer_user_tool` may be true only for `OFFER_CUSTOMER_OPERATED_TOOL`. Treat malformed input, `INVALID_INPUT`, or an unexpected response as a reason to pause rather than offer a link.

## Decision handling

### No active documented program

For `REFUSE_NO_ACTIVE_DOCUMENTED_PROGRAM`, explain that no active, card-specific referral program has been documented for the requested card, so the claimed offer cannot be validated and a referral link cannot be provided.

Do not provide a referral URL, link-generator instructions, or a customer referral-link tool. Do not transfer the customer merely because they request escalation for this unsupported offer.

Every refusal response for a referral request should also include the documented limit in clear customer-facing language:

> Customers can receive at most two referral bonuses in any rolling seven-day period; third and later referrals in that window are automatically denied.

If the customer asks to be transferred solely to obtain a link for the undocumented or unvalidated offer, decline clearly without transferring. For example, state: "I can't transfer this request solely to obtain a referral link for an offer that cannot be validated." Continue to explain the documentation issue, but do not invoke a human-transfer action.

### Terms mismatch

For `REFUSE_TERMS_MISMATCH`, identify the relevant documented terms and explain that the claimed offer does not match the active documented program. Do not provide a link, referral-link tool, or transfer merely because of this discrepancy. Include the rolling-seven-day/two-bonus reminder above.

### Terms need confirmation

For `NEEDS_CUSTOMER_TERM_CONFIRMATION`, restate the verified card-specific terms and request confirmation. Do not offer the tool until confirmation is recorded. Include the rolling-seven-day/two-bonus reminder.

### Automatic denial expected

For `REFUSE_AUTOMATIC_DENIAL`, explain the reliable factual basis for the expected denial. State that customers can receive at most two referral bonuses in any rolling seven-day period and that third and later referrals in that window are automatically denied. Do not provide a link or transfer solely for this reason.

### All checks pass

For `OFFER_CUSTOMER_OPERATED_TOOL`, reiterate the verified terms and the rolling-seven-day two-bonus limit. Provide the customer-operated `get_referral_link` through `give_discoverable_user_tool`; do not call it or generate a link on the customer's behalf.

Tell the customer to enter their own `user_id` and the exact `documented_card_name`. A successful customer call creates a referral record with status `NO_PROGRESS`, after which the referred person may use the generated link to apply.

## Assessment script interface

Run `scripts/assess_referral_request.py` with one JSON object on standard input. It writes one JSON object to standard output.

Input fields:

- `requested_card_name` (string): Name requested by the customer.
- `card_identity_confirmed` (boolean): True only when documentation unambiguously maps the requested card to `documented_program.card_name`.
- `documented_program` (object or `null`): `null` when no specific program is documented. Otherwise contains `card_name` (string), `active` (boolean), and `terms` (object).
- `claimed_terms` (object): Every term the customer actually claimed, using the same canonical keys and units as `documented_program.terms`. Use `{}` only if no terms were claimed.
- `customer_confirmed_documented_terms` (boolean): True only after confirmation of the complete documented terms.
- `automatic_rejection_expected` (boolean): True only when reliable available information establishes expected automatic denial.
- `automatic_rejection_reason` (string): Required when automatic rejection is expected; provide the factual basis without speculation.

The caller must perform card research and canonicalize comparable values. Do not infer a card match from a similar name or replace unavailable documentation with a customer-provided offer.

Example safe invocation:

```sh
python3 scripts/assess_referral_request.py <<'JSON'
{"requested_card_name":"","card_identity_confirmed":false,"documented_program":null,"claimed_terms":{},"customer_confirmed_documented_terms":false,"automatic_rejection_expected":false}
JSON
```

The output may include `mismatched_term_keys`, `documented_card_name`, and `documented_terms`. Use documented fields only when they came from verified card-specific material, and always use the exact documented card name when offering the customer-operated tool.

See `references/referral_policy.md` for the concise governing policy.