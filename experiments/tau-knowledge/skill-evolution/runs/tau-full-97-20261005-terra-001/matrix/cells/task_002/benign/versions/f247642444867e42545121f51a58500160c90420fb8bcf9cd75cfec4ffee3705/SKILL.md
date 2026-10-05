---
name: highest-flat-cash-back-card
version: 1.1.0
description: Recommend exactly one personal Rho-Bank card for a request for the highest cash back on everyday purchases, using supplied product terms to select the unique highest documented flat all-purchases cash-back rate.
---

# Highest Flat Cash-Back Card Recommendation

## When to use
Use this Skill for a customer asking for one Rho-Bank card with the best cash back for ordinary or everyday spending. Treat everyday spending as a documented **flat rate on all eligible purchases**. A category-only bonus, such as travel or software, does not meet that criterion.

This is product information, not an approval decision. Do not use a customer's title, employer, or inferred finances as eligibility evidence. Do not access customer data, submit an application, or make account changes.

## Required method
1. Read the product documents and evidence supplied with the current task. Supplied product terms are evidence: do not say that terms are unavailable merely because no external search was performed.
2. Build one record per personal card with a documented flat cash-back rate. Reconcile multiple documents for the same card. Include:
   - the card name;
   - the documented flat rate on all eligible purchases;
   - annual fee, if documented;
   - explicit application/access constraints, if documented;
   - eligibility and reward conditions; and
   - at least one source identifier or faithful source quotation.
3. Do not treat a category-limited rate as a flat everyday rate. Do not treat rewards points as cash back unless the supplied evidence explicitly establishes the cash-equivalent conversion.
4. An explicit invitation-only restriction makes a card unavailable for an ordinary application recommendation. A stated minimum credit score or subscription prerequisite is a constraint to disclose, not a reason to silently omit a card.
5. Send the records to `scripts/recommend.py`. The script selects only a unique qualifying maximum; it returns `needs_review` for missing data or a tie.
6. If the result is `ok`, use its `customer_message` verbatim or preserve its first two sentences exactly. Give no second recommendation, no ranked list, and no unsupported refusal.
7. If the result is `needs_review`, explain only the documented gap or tie and request the missing terms. Do not invent a tie-breaker.

## Customer-response requirements
For a successful selection, the response must begin with a decisive singular recommendation in this form:

> I recommend the **[card name]**. It earns **[rate]% cash back on all eligible purchases**—the highest documented flat rate for everyday spending.

Then, concisely disclose supported material conditions, such as an annual fee, a minimum credit-score requirement, qualifying-purchase exclusions, posting timing, or return adjustments. A fee or score requirement is not an approval determination.

Do not name another card as a recommended alternative. Do not claim that a customer qualifies or will be approved.

## Script interface
Run:

```text
python scripts/recommend.py < candidates.json
```

The input is one JSON object:

```json
{
  "cards": [
    {
      "name": "string",
      "personal": true,
      "cash_back_rate_percent": 0,
      "applies_to_all_eligible_purchases": true,
      "ordinary_application_available": true,
      "annual_fee": 0,
      "eligibility_constraints": ["documented requirement"],
      "conditions": ["documented reward condition"],
      "evidence": ["document ID or source quotation"]
    }
  ]
}
```

Required fields are `name`, `personal`, `cash_back_rate_percent`, `applies_to_all_eligible_purchases`, and nonempty `evidence`. `ordinary_application_available` defaults to `true` when no invitation-only or comparable restriction is documented. `annual_fee` may be `null`; the lists may be empty except for `evidence`.

Output is JSON. On success it has:

```json
{
  "status": "ok",
  "recommendation": {"name": "...", "cash_back_rate_percent": "..."},
  "customer_message": "I recommend the ..."
}
```

On incomplete data or a tie it has `status: "needs_review"` and a source-neutral reason.

## Final validation
Before responding, confirm all of the following:
- The selected rate explicitly applies to all eligible purchases.
- The selection is the unique highest documented qualifying personal-card rate.
- The response says “I recommend the [selected card]” and communicates the percentage and all-purchases/everyday connection.
- Exactly one card is presented as a recommendation.
- Every disclosed fee, prerequisite, and condition is supported by the supplied records.
