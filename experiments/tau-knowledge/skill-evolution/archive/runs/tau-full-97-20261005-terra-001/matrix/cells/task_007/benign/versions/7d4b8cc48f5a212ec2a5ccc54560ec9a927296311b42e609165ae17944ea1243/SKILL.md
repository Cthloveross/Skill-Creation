---
name: credit-card-signup-bonus-recommender
description: Evaluate documented credit-card sign-up awards as of a supplied date and recommend the best currently available personal or business offer. Use when promotion windows, invitation status, new-customer eligibility, spending requirements, annual fees, and points-to-cash conversion must be compared.
---

# Credit-card sign-up bonus recommender

Use this Skill for informational card-shopping comparisons. Do not apply for a card, access an account, determine underwriting eligibility, or claim that a customer will be approved.

## Complete the comparison in the current response

After the customer supplies sufficient preferences or answers a necessary clarification, inspect the supplied task documents and give the completed comparison in the next substantive response. Do **not** reply only that a comparison can be made, promise to review offers later, or claim that source data is unavailable when offer documents are supplied in the task context.

Write the customer-facing answer as normal prose or a compact table, not as a JSON wrapper. The conclusion must name the selected card and its actual bonus terms; a generic explanation of the comparison method is not a completed answer.

## Gather facts from the current task materials

Use the supplied documents and observations, not assumptions, to determine:

1. The as-of date. Prefer a supplied current-time observation; otherwise state the date limitation.
2. Requested audience: personal, business, or either.
3. Whether the customer is a new customer, not a new customer, or this is unknown.
4. Whether the customer has each required invitation.
5. Each documented positive sign-up award: card, audience, campaign start/end dates, reward amount and unit, spend threshold, qualification period, award conditions, and source.
6. The selected card's annual fee when the user asks about fees or when it is material to the comparison.
7. A documented points redemption rate before describing points in dollars.

A positive sign-up award is an award of points, cash back, or a statement credit. Do not substitute a standard earn rate, an APR promotion, ordinary application terms, or an annual-fee waiver for a points/cash sign-up bonus. A fee waiver may be mentioned separately if relevant.

## Evaluate availability before ranking

Build a candidate list from **all** documented positive sign-up awards before drafting. For each candidate:

- A date window is inclusive: active means `start <= as-of date <= end`.
- Exclude campaigns that have not started, have ended, target the wrong requested audience, or require an invitation the customer says they do not have.
- Exclude a new-customer-only offer only when the customer is known not to be new. If new-customer status is unknown, keep an otherwise active offer as conditional and clearly say it requires new-customer eligibility.
- Treat incomplete campaign-date evidence as unverified, not as active.
- Do not infer a reward, fee, audience, conversion rate, or eligibility term from a different card.

A required invitation is decisive: do not present an invitation-only bonus as an available option when the customer lacks that invitation. If it is useful to mention a larger excluded award, immediately state both that it requires an invitation and that it is unavailable to this customer.

Use `scripts/rank_signup_offers.py` after extracting the facts when practical. The script has no document retrieval capability: the executor must provide the current task's extracted evidence as JSON. Its result is a check on date, eligibility, and cash-equivalent ranking; it does not replace reading the source documents or composing the response.

**Hard response gate:** Never state that there are no documented current sign-up awards until every positive-award candidate has been checked against the as-of date and classified as excluded, unverified, or unrankable. If one or more eligible offers remain, recommend the highest documented cash-equivalent one. If no eligible offer remains but an active conditional offer remains, identify it as conditional and state the unresolved eligibility condition.

## Value comparison

Rank simultaneously available, eligible candidates by documented cash-equivalent sign-up value:

- Statement credits and explicitly dollar-denominated cash awards are worth their stated USD amount.
- Convert points only when the supplied documents give a redemption rate.
- State both the native point award and its documented redemption value. Never relabel a number of points as the same number of dollars.
- If no conversion is documented, retain the native reward and say that a dollar-value ranking cannot be established for it.

The spending requirement is a qualification term, not a subtraction from the bonus value. Still disclose it prominently so the customer can judge whether the offer is practical.

## Required customer-facing content

For a positive recommendation, include all applicable items below:

1. The card name and that it is the best documented currently available (or conditional) sign-up award for the requested audience as of the observed date.
2. The exact native reward, including its unit.
3. The exact eligible-purchase threshold and qualification period after opening.
4. Campaign end date (and start date when useful), plus documented new-customer and good-standing conditions.
5. The documented dollar redemption equivalent for points, if available, stated accurately.
6. The selected card's documented annual fee if the customer asked for annual-fee information.
7. Why a material larger, expired, wrong-audience, or invitation-only alternative is excluded. Do not imply the customer can obtain an unavailable offer.
8. That the conclusion is limited to the documented offers provided for this task, and the relevant source document title or ID.

Use a direct structure such as:

```text
Recommendation: [Card] is the highest-value documented currently [available/conditional] [audience] sign-up award as of [date].
Bonus and qualification: Earn [native reward] after [eligible spend] within [period] after opening. [Campaign dates and documented eligibility terms.]
Value and fee: [documented redemption rate/equivalent]. Annual fee: [documented fee].
Comparison note: [why each material alternative is excluded].
Sources: [offer source; conversion source; fee source].
```

If there is no eligible or conditional current award after the hard response gate, state that result narrowly and identify the documented reason each relevant candidate is excluded. Do not recommend an expired, unsupported, or unavailable promotion.

## Ranking-script interface

`scripts/rank_signup_offers.py` reads exactly one JSON object from standard input and writes exactly one JSON object to standard output. It makes no network requests and performs no customer actions.

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

Supply `invited_offer_ids: []` when the customer has said they have no invitation. Omit `invited_offer_ids` only when invitation status is unknown. `is_new_customer` may be `true`, `false`, omitted, or `null`; omitted and `null` mean unknown.

Output contains `eligible`, `conditional`, `excluded`, `unverified`, `unrankable`, `recommendation`, and `validation`. Before relying on a positive selection, verify `ok`, `validation.recommendation_is_current`, and `validation.selection_is_maximum_in_selected_pool`. Also ensure the final prose discloses every selected condition and contains only conversions and fees supported by supplied documents.

A runnable invocation using an executor-created extraction file is:

```sh
python3 scripts/rank_signup_offers.py < extracted_offers.json
```

Malformed JSON or malformed extracted fields yield `{"ok": false, "error": "..."}`. Correct the extraction from the supplied source instead of guessing.