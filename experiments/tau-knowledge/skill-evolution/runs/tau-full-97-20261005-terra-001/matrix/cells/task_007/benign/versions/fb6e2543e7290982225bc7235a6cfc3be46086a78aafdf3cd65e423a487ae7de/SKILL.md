---
name: credit-card-signup-bonus-recommender
description: Compare documented credit-card sign-up awards as of an observed date and recommend the best currently available personal or business offer. Use when offer dates, invitation status, new-customer eligibility, spending requirements, annual fees, and points-to-cash conversion must be evaluated.
---

# Credit-card sign-up bonus recommender

Use this Skill for an informational card-shopping comparison. Do not apply for a card, access a customer account, determine underwriting eligibility, or promise approval.

## Completion rule

When the task context already contains an observed date, relevant offer documents, and the user's audience/invitation clarification, provide the **completed comparison in the next substantive customer-facing response**. Do not send an acknowledgement, a plan, a JSON object, or a statement that comparison is possible. Do not claim that no source data or current offer list is available when the supplied task documents contain offer information.

The final answer must be ordinary prose or a compact table. It must explicitly name the recommended card and state the selected offer's actual terms. A generic discussion of how offers would be compared is not a completed answer.

## Extract evidence from the current task

Read every supplied document that could describe a promotion, card fee, reward representation, or invitation requirement. Use the supplied observation for the as-of date. Build a candidate list before writing.

For every documented positive sign-up award, extract:

- card and requested audience, if documented;
- campaign start and end dates;
- reward amount and native unit;
- eligible-purchase threshold and qualification period;
- new-customer, account-good-standing, and other material conditions;
- invitation requirement and whether the customer has the invitation;
- documented reward conversion rate, if any;
- annual fee when the user asks about fees; and
- source title or document ID.

A positive sign-up award means points, cash back, a cash award, or a statement credit. Do **not** treat an ordinary earn rate, an APR offer, application terms, or an annual-fee waiver as a points/cash sign-up award. Mention such features separately only if helpful.

## Availability and ranking procedure

1. Use the full calendar date from the observed current-time result. A campaign window is inclusive: an offer is active only if `start <= as-of date <= end`.
2. Exclude an award that has not started, has ended, targets the wrong requested audience, or requires an invitation that the customer has said they lack.
3. Exclude new-customer-only offers only if the customer is known not to be new. If status is unknown, retain an otherwise active offer as conditional and clearly state that it requires new-customer eligibility.
4. Treat an award with a missing start or end date as unverified; never assume it is active.
5. Rank eligible offers by documented cash-equivalent award value. A statement credit or explicitly dollar-denominated award has its stated value. Convert points only using a supplied documented redemption rate.
6. If no fully eligible candidate remains but an active conditional candidate remains, identify the highest-value conditional candidate and state its unresolved condition. Only say that no current award is available after each positive-award candidate has been classified.

A required invitation is decisive. Do not present an invitation-only bonus as available if the customer lacks the invitation. If it is materially larger and mentioned for context, immediately state that it requires an invitation and is unavailable to the customer.

Do not subtract a spending requirement or annual fee from a bonus to invent a "net bonus" unless the user expressly requests a net-cost calculation. Disclose both prominently instead.

Use `scripts/rank_signup_offers.py` after evidence extraction when practical. The script has no retrieval ability: it evaluates only facts supplied in its JSON input. Its output is a consistency check, not a substitute for reading the documents or writing the response.

## Mandatory final-response checklist

Before sending a positive recommendation, verify that the response includes:

- the selected card name and that it is the highest documented currently available (or conditional) award for the requested audience as of the observed date;
- the exact native reward amount and unit;
- the exact eligible-purchase threshold and qualification period after opening;
- campaign dates, new-customer condition, and good-standing condition when documented;
- the documented conversion rate and resulting dollar redemption value for a points award, without relabeling points as the same number of dollars;
- the selected card's documented annual fee when the user requested annual-fee information;
- why each material higher-value, expired, or invitation-only alternative is excluded; and
- a limitation that the conclusion is based on the documented offers supplied for this task, with relevant sources.

Use direct language such as:

```text
Recommendation: [Card] is the highest-value documented currently available [audience] sign-up award as of [date].
Bonus and qualification: Earn [native reward] after [eligible spend] within [period] after opening. [Campaign dates and conditions.]
Value and fee: [documented redemption rate and equivalent]. Annual fee: [documented fee].
Comparison note: [why material alternatives are excluded].
Sources: [source IDs or titles].
```

If no candidate is available, state that conclusion narrowly, list the documented exclusion reason for each relevant award, and do not recommend an expired or unavailable promotion.

## Script interface

`scripts/rank_signup_offers.py` reads exactly one JSON object from stdin and writes exactly one JSON object to stdout. It performs no network, account, application, or banking action.

Input schema:

```json
{
  "as_of": "ISO-8601 timestamp or YYYY-MM-DD",
  "desired_audience": "personal | business | any",
  "invited_offer_ids": ["offer IDs for invitations the customer has"],
  "is_new_customer": true,
  "offers": [
    {
      "id": "stable extracted offer ID",
      "card_name": "display name",
      "audience": "personal | business | any",
      "offer_start": "YYYY-MM-DD",
      "offer_end": "YYYY-MM-DD",
      "requires_invitation": false,
      "new_customer_required": true,
      "spend_requirement_usd": "optional decimal",
      "qualification_months": "optional number",
      "annual_fee_usd": "optional documented decimal",
      "reward": {
        "amount": "positive decimal",
        "unit": "native reward unit",
        "conversion_usd_per_unit": "optional documented decimal"
      },
      "terms": ["documented material condition"],
      "source": {"document_id": "source ID", "title": "source title"}
    }
  ]
}
```

If the customer explicitly has no invitations, pass `"invited_offer_ids": []`. Omit that field only when invitation status is unknown. `is_new_customer` can be `true`, `false`, omitted, or `null`; omitted and `null` mean unknown.

The output has `eligible`, `conditional`, `excluded`, `unverified`, `unrankable`, `recommendation`, and `validation` fields. Before relying on a selection, ensure `ok` is true and that `validation.recommendation_is_current` and `validation.selection_is_maximum_in_selected_pool` are true.

Example runnable invocation with an executor-created extraction file:

```sh
python3 scripts/rank_signup_offers.py < extracted_offers.json
```

Malformed JSON or malformed extracted fields produce `{"ok": false, "error": "..."}`. Correct the extraction from the supplied documents rather than guessing.