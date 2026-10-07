---
name: credit-card-referral-link-gating
description: Assess a credit-card referral-link request after knowledge-base review. Use when a customer asks for a referral link or describes a referral promotion. It prevents referral-link delivery unless the requested card and stated terms are documented and no automatic-denial condition applies.
---

# Credit-card referral-link gating

## Purpose

Use this Skill before offering a customer any referral-link capability. The referral procedure is conditional: a documented program for the exact card, matching customer-facing terms, and no known automatic-denial risk are all required.

This Skill only assesses eligibility and supplies response guidance. It never generates a link, calls a banking tool, looks up customer data, or transfers a customer.

## Required pre-check

1. Search the available knowledge base for a referral program for the **exact requested card name**.
2. Record the documented terms for every matching program and compare the customer's claimed offer terms with those terms.
3. Determine whether a referral would be automatically denied. In particular, a customer can receive no more than two referral bonuses in any rolling seven-day window; the third and later referrals in that window are automatically denied.
4. Run `scripts/assess_referral.py` using the reviewed facts. Do not treat an unperformed or inconclusive search as proof that a program does not exist.

The packaged reference, `references/referral-policy.md`, is a policy source available to this Skill. It does not establish a program for a particular card. A card-specific program must be found in the runtime knowledge-base material before a link can be offered.

## Script interface

Run:

```text
python3 scripts/assess_referral.py < assessment.json
```

The script reads one JSON object from standard input and emits one JSON object to standard output. Its input fields are:

- `requested_card` (string, required): exact card name requested by the customer.
- `knowledge_search_completed` (boolean, required): true only after the relevant knowledge base was searched.
- `documented_programs` (array, required): card-program records found in that search. Each record has `card_name` (string), optional `program_documented` (boolean; defaults to true), and `terms` (string, array, object, or null).
- `claimed_terms` (string, array, object, or null): the offer terms asserted by the customer. Use null when the customer did not state terms.
- `claimed_terms_match` (boolean or null): set this from the human/KB comparison. Use `false` if the claim conflicts with documented terms, `true` if it matches, and `null` if a stated claim still needs comparison.
- `referrals_in_rolling_7_days` (non-negative integer, optional): prior referrals relevant to the documented weekly limit, when reliably available.
- `automatic_rejection_risk` (boolean, optional): true when another documented reason indicates automatic denial.

The output has a `decision`, `reasons`, `documented_terms`, `user_tool`, and `next_step`. Decisions are:

- `SEARCH_REQUIRED`: knowledge-base review has not been completed.
- `DECLINE_UNDOCUMENTED_PROGRAM`: no documented referral program exists for the requested card.
- `TERM_COMPARISON_REQUIRED`: customer stated terms but the comparison is unresolved.
- `DECLINE_TERMS_MISMATCH`: the customer's stated terms conflict with the documented program.
- `DECLINE_AUTOMATIC_REJECTION`: a known limit or other condition means the referral would automatically be denied.
- `OFFER_SELF_SERVICE_REFERRAL_TOOL`: all gates passed.

The script deliberately does not infer semantic equivalence between differently worded promotional terms. The executor must make that comparison from the documented program and pass `claimed_terms_match`.

## Completing the customer response

### When the result is a decline

For `DECLINE_UNDOCUMENTED_PROGRAM`, explain that no referral program is documented for the requested card, so a referral link cannot be provided.

For `DECLINE_TERMS_MISMATCH`, state the correct documented terms and explain that the described offer does not match the documented program, so a referral link cannot be provided.

For `DECLINE_AUTOMATIC_REJECTION`, explain the applicable automatic-denial reason, including the rolling seven-day limit when that is the reason. Do not provide a referral-link tool.

Do not transfer to a human for any of those three outcomes. Do not offer a workaround or generate a link on the customer's behalf.

For `SEARCH_REQUIRED` or `TERM_COMPARISON_REQUIRED`, complete the missing knowledge-base review before promising a link. If the runtime cannot establish the required facts, do not present a referral link as available.

### When the result permits self-service

Only for `OFFER_SELF_SERVICE_REFERRAL_TOOL`:

1. Reiterate the documented terms returned in `documented_terms`.
2. Use the execution agent's user-tool delivery mechanism to provide `get_referral_link`; do not call it as an agent.
3. Tell the customer to run `get_referral_link(user_id, card_name)` themselves, using their own user ID and the exact requested card name.
4. Explain that successful use creates a referral record with status `NO_PROGRESS`, after which the referred person may apply with the generated link.
5. Remind the customer that at most two referral bonuses may be received in a rolling seven-day window and later referrals in that window are automatically denied.

Do not populate or obtain a user ID solely to generate the link for the customer. The customer, not the agent, executes the referral-link tool.

## Validation

Before responding, verify all of the following:

- A completed KB search supports a card-specific documented program.
- Any customer-claimed offer has been affirmatively compared with documented terms.
- Automatic denial has been ruled out, including the two-bonus rolling seven-day cap when relevant facts are available.
- The referral capability is delivered only in the permitted self-service outcome.
- Every refusal explains why; no refusal for undocumented, mismatched, or automatically denied referrals is transferred to a human.
