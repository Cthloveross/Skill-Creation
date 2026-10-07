---
name: credit-card-signup-bonus-advisor
description: Compare documented credit-card promotional sign-up bonuses for a customer, determine time and eligibility applicability, normalize points to cash value only when documented, and provide an evidence-grounded recommendation without opening or changing an account.
---

# Credit Card Sign-up Bonus Advisor

Use this skill when a customer asks which credit card has the best current sign-up bonus, especially where the priority is points, cash back, or statement-credit value. It is for informational comparison, not for applying for a card, enrolling an offer, or changing an account.

## Inputs to collect

Use only supplied, current offer documents and read-only observations. Collect or identify:

- Current date, preferably from a read-only time observation.
- Whether the customer seeks a personal or business card.
- New-customer status where an offer requires it.
- Invitation status where an offer requires an invitation.
- Expected qualifying spend if known. If unknown, do not assume the customer can meet a spend threshold.
- For each offer: product, offer-window dates, benefit type and amount, spend requirement and period, eligibility conditions, exclusions, fulfillment conditions, and any documented points-to-currency conversion.

Ask only for facts that materially change the recommendation. If spend capacity is unknown and the customer asks to see offers first, present the available conditional offer(s) and clearly state the threshold rather than blocking the answer.

## Method

1. **Define the comparison scope.** For a request prioritizing a sign-up bonus, include direct new-account points, cash-back, and statement-credit bonuses. Keep APR promotions, fee waivers, and ongoing earn rates separate; do not portray them as cash/points sign-up bonuses.
2. **Check dates inclusively.** An account-opening date on either endpoint of a documented offer window is in-window. Do not infer that an offer without a current documented window is available.
3. **Check every explicit condition.** Evaluate product type, new-customer requirement, invitation requirement, spend threshold and measurement period, account-open/good-standing requirements, and transaction exclusions. A failed condition makes an offer unavailable; an unknown condition makes it conditional, not confirmed.
4. **Normalize value conservatively.** State a dollar equivalent for points only when the documents provide a redemption conversion. Do not call points and cash back equivalent otherwise. Use the documented conversion and show both the original benefit and equivalent value.
5. **Rank only like-for-like offers.** Rank active offers satisfying known eligibility conditions by documented cash-equivalent bonus value. If the customer's ability to satisfy a spend threshold is unknown, identify the leading offer as conditional rather than saying they will receive it. Qualitative benefits must not be assigned invented dollar values.
6. **Explain notable exclusions.** Briefly distinguish expired direct bonuses, invitation-only offers without an invitation, and active non-bonus promotions when that prevents a misleading comparison.
7. **Respond with bounded certainty.** Say “best among the documented offers” rather than claiming a market-wide best. Cite the relevant supplied document titles or identifiers in the response.

Use `scripts/rank_promotions.py` after converting the supplied documents into the structured input described below when there are several offers or date/eligibility comparisons. The script assists with deterministic filtering and value ordering; the executor remains responsible for faithfully extracting offer terms and explaining terms that the script does not model.

## Customer-facing response pattern

Produce a short, direct answer containing:

1. The recommended product and its direct bonus, with points and documented cash equivalent where applicable.
2. The exact opening window and every material qualification condition, including the spend amount and deadline.
3. A clear statement that the recommendation is conditional if spend ability or another required fact is unknown.
4. Why stronger-looking alternatives are not currently comparable (for example, expired, invitation-only, or APR-only).
5. A targeted next question only if it changes the decision, such as whether the customer can meet the required eligible spend in the stated period.

Do not fabricate application approval, credit limits, merchant eligibility, posting dates, a redemption channel, or a bonus amount. Do not promise bonus fulfillment; describe documented timing and conditions instead.

## No account action in this workflow

General product advice based on supplied documents does not require looking up customer records or identity verification. Do not access customer accounts merely to make a general offer comparison. Do not apply, open an account, redeem rewards, or make any other banking change as part of this skill.

If the request changes into a banking action, first follow the applicable tool and authorization process. Preserve this mandatory prerequisite verbatim with that resulting procedure:

> Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Promotion-ranking script

Run `scripts/rank_promotions.py` with JSON on stdin. It emits JSON on stdout and uses only the Python standard library.

### Input schema

```json
{
  "current_date": "YYYY-MM-DD",
  "customer": {"new_customer": true, "has_invitation": false},
  "target_benefit_kinds": ["cash_back", "statement_credit", "points"],
  "offers": [
    {
      "id": "optional-source-key",
      "product": "Product name",
      "audience": "personal",
      "open_start": "YYYY-MM-DD",
      "open_end": "YYYY-MM-DD",
      "benefit": {
        "kind": "points",
        "amount": "1000",
        "unit": "points",
        "point_value_usd": "0.01"
      },
      "requirements": [
        {"field": "new_customer", "equals": true, "label": "must be a new customer"}
      ],
      "spend_requirement": {"amount_usd": "1000", "period_months": 3},
      "notes": ["optional documented condition or exclusion"]
    }
  ]
}
```

`requirements` compares each `field` with the corresponding value in `customer`. Missing customer values are treated as unknown. Use `cash_value_usd` in `benefit` when the document directly provides a cash value; otherwise a non-USD benefit needs `point_value_usd` before the script will calculate a cash equivalent. Dates must be ISO calendar dates. Omit no-date offers from a claim that an offer is currently active; the script labels them as date-unknown.

### Output schema and validation

On valid input, the script returns `ok: true` and these lists:

- `ranked_candidates`: active, targeted benefits that are eligible or conditional, ordered with confirmed eligibility before conditional eligibility and then by known cash value.
- `active_nontargeted`: active offers outside the requested benefit kinds, useful for labeling APR or fee promotions separately.
- `excluded`: offers excluded for inactive dates, failed eligibility, unknown dates, or missing benefit data.

Each result has date status, eligibility status and reasons, normalized `cash_value_usd` when calculable, plus the documented spend requirement and notes. On malformed input it returns `ok: false` with actionable `errors`; correct the extracted data rather than guessing.

Example runnable call shape (use values extracted from the live task documents, not this illustrative schema):

```sh
python scripts/rank_promotions.py <<'JSON'
{"current_date":"YYYY-MM-DD","customer":{},"target_benefit_kinds":[],"offers":[]}
JSON
```

Before relying on the result, verify that each included candidate has an active date status, a target benefit kind, no failed requirements, and a cash conversion only where the source explicitly documents one.