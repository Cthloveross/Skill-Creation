---
name: credit-card-referral-link-review
description: Safely handle a request for a credit-card referral link. Use when a customer names a card and may cite referral-offer terms; it verifies card-specific documentation, claimed terms, and likely automatic denial before offering the customer-operated referral-link tool.
---

# Credit Card Referral Link Review

## Purpose

A referral-link tool may be offered only after all of the following are true:

1. The requested, specific card has an active, card-specific documented referral program.
2. The customer's stated offer terms match that documented program and the customer has confirmed the documented terms.
3. There is no reason to believe the referral would be automatically denied.

General referral-program material is not evidence that a particular card participates. A mailed offer, customer recollection, or claimed bonus is likewise not sufficient without matching card-specific documentation.

## Required review procedure

1. Search the available knowledge base for the requested card's referral program. Resolve the card identity unambiguously; retain the exact documented card name.
2. Locate the active program's customer-visible material terms, including the reward, whose reward it is, qualifying approval/account conditions, spending requirement, qualification period, and any other stated restrictions.
3. Compare every term the customer cited with the corresponding documented term. If a cited term is absent from the documentation or differs, explain the discrepancy. Do not offer a referral link.
4. Restate the documented terms and obtain the customer's confirmation when needed. If confirmation has not yet been obtained, ask for it; do not offer the tool yet.
5. Consider automatic denial. A customer can receive at most two referral bonuses in any rolling seven-day window. If available, reliable referral information or the customer's statement establishes that this would be the third or later qualifying referral in that window, explain that it will be automatically denied and do not offer a link. Do not treat an unknown referral history as proof of denial.
6. Use `scripts/assess_referral_request.py` after converting the search findings and the customer's statements into the structured input described below. The script is a deterministic guardrail; it does not search the knowledge base or perform banking actions.

## Decision handling

- `REFUSE_NO_ACTIVE_DOCUMENTED_PROGRAM`: Explain that no active referral program is documented for the requested card, so a referral link cannot be provided.
- `REFUSE_TERMS_MISMATCH`: Identify the documented terms relevant to the mismatch, clarify that the claimed offer does not match the documented program, and do not provide a link.
- `NEEDS_CUSTOMER_TERM_CONFIRMATION`: Reiterate the documented card-specific terms and request confirmation. Do not provide a link until confirmation is recorded in the assessment input.
- `REFUSE_AUTOMATIC_DENIAL`: Explain the rolling seven-day maximum of two referral bonuses and the specific available basis for believing this referral would be denied. Do not provide a link.
- `OFFER_CUSTOMER_OPERATED_TOOL`: Reiterate the documented terms and the weekly limit. Then provide the customer-operated tool `get_referral_link` using `give_discoverable_user_tool`. Do not call or generate the referral link as the agent.

For the offered tool, tell the customer that they must enter **their own** `user_id` and the **exact documented card name**. A successful customer call creates a referral record with status `NO_PROGRESS`; the referred person may then use the generated link to apply.

When refusing because the program is undocumented, terms mismatch, or automatic denial is expected, do **not** transfer the customer to a human agent merely for that reason. Do not unlock or call an agent discoverable referral-link tool.

## Assessment script interface

Run `scripts/assess_referral_request.py` with one JSON object on standard input. It writes one JSON object to standard output.

Input schema:

- `requested_card_name` (string): Card name requested by the customer.
- `card_identity_confirmed` (boolean): `true` only when knowledge-base review unambiguously maps the request to `documented_program.card_name`.
- `documented_program` (object or `null`): `null` if no specific program was found. Otherwise it has:
  - `card_name` (string): Exact documented card name.
  - `active` (boolean): Whether the documented program is active.
  - `terms` (object): Canonical customer-visible documented terms keyed consistently with `claimed_terms`.
- `claimed_terms` (object): Every term actually claimed by the customer, converted into the same canonical key/value representation as the documentation. An unknown claimed term must remain present so it is treated as a mismatch. Use `{}` only when the customer stated no terms.
- `customer_confirmed_documented_terms` (boolean): `true` only after the customer has confirmed the complete documented terms.
- `automatic_rejection_expected` (boolean): `true` only with a reliable, stated basis that the referral will be automatically denied.
- `automatic_rejection_reason` (string): Required when `automatic_rejection_expected` is `true`; state the factual basis without adding unsupported assumptions.

The caller, not the script, must canonically represent comparable values. For example, use the same field names and units for a spending amount and qualification period in both term objects. Do not attempt to infer a card match from similar names or to replace missing documentation with a customer-provided offer.

A minimal runnable safe invocation is:

```sh
python3 scripts/assess_referral_request.py <<'JSON'
{"requested_card_name":"","card_identity_confirmed":false,"documented_program":null,"claimed_terms":{},"customer_confirmed_documented_terms":false,"automatic_rejection_expected":false}
JSON
```

## Output validation

Before acting on script output, confirm that it is a JSON object, `decision` is one of the five decisions listed above, and `may_offer_user_tool` is `true` **only** for `OFFER_CUSTOMER_OPERATED_TOOL`. Treat malformed input, an `INVALID_INPUT` result, or any unexpected result as a reason to pause and obtain/validate the required information; do not offer the tool.

The script returns `mismatched_term_keys` for a terms-mismatch decision. Use `documented_card_name` and `documented_terms` only when they were supplied by the verified card-specific documentation. Always use the exact `documented_card_name`, not a normalized customer spelling, in customer instructions for `get_referral_link`.

See `references/referral_policy.md` for the governing referral-link constraints.