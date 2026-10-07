---
name: credit-card-signup-bonus-advisor
description: Compare supplied credit-card promotions for a customer seeking a points, cash-back, or statement-credit sign-up bonus; determine current availability and eligibility; calculate a documented cash equivalent; and give a grounded informational recommendation without taking account action.
---

# Credit Card Sign-up Bonus Advisor

Use this skill for an informational request to find or compare a current credit-card sign-up bonus, particularly when a customer prioritizes points, cash back, or a statement credit. This is product advice only: do not apply for a card, open an account, access customer accounts, or redeem rewards.

## Required inputs and evidence use

Treat the task's supplied frozen documents and read-only observations as the offer corpus for this request. Before answering, inspect every document relevant to the requested audience and promotion type; do not say that offer terms or documents are unavailable when supplied documents describe them.

Collect or identify:

- The observed current date (prefer a supplied read-only time observation).
- Whether the requested card is personal or business.
- New-customer status if required by an offer.
- Invitation status if an offer is invitation-only.
- Expected eligible spend, if the customer knows it.
- For every potentially relevant offer: product, opening window, benefit type and amount, spend requirement and qualifying period, eligibility conditions, account-status requirements, transaction exclusions, fulfillment timing, and any documented point-redemption conversion.

Ask only questions whose answer materially changes the comparison. If the customer asks what is available before providing an expected spend amount, present the currently available offer(s) conditionally and identify the spend threshold as the decision point. Do not withhold the offer comparison or assume that the customer can meet the threshold.

## Comparison method

1. **Limit the scope to the request.** For a points/cash sign-up-bonus request, compare direct new-account points, cash-back, and statement-credit bonuses. Keep APR promotions, annual-fee waivers, and ongoing rewards rates in a separate non-bonus category.
2. **Determine date availability.** Compare the observed date to each documented application/account-opening window inclusively. An offer is current only when the date is on or between both endpoints. An offer with no documented active window must be labeled date-unknown, not current.
3. **Determine applicability.** Check audience, new-customer status, invitation status, and every explicit offer condition. A known unmet condition excludes an offer. An unknown condition makes it conditional rather than unavailable or guaranteed.
4. **State all material terms for a recommended candidate.** Include the product, direct bonus amount and unit, opening window, required qualifying spend, measurement period, customer-status requirement, and requirement to keep the account open and in good standing where documented. Mention important purchase exclusions when supplied.
5. **Normalize cautiously.** Convert points to dollars only if the supplied documents explicitly give a redemption rate. Show the arithmetic in plain language: bonus points × documented dollars per point = approximate redeemable value. Clearly distinguish a points total from its dollar value; never imply that an amount of points is the same amount in cash.
6. **Rank comparable candidates.** Rank active, applicable or conditional direct bonuses by their documented cash-equivalent value. Say “best among the documented offers,” not “best available anywhere.” If only one direct-bonus candidate remains, identify it as the current documented option rather than claiming a broader market comparison.
7. **Prevent misleading alternatives.** Briefly explain why a seemingly stronger offer is not comparable when relevant: expired window, invitation requirement not met, unmet eligibility, or an APR/fee promotion rather than a direct points/cash bonus. Never describe an expired direct bonus as current or substitute a 0% APR offer for the requested sign-up bonus.
8. **State uncertainty accurately.** Approval is never assured. If the customer's spend ability is unknown, say the bonus is conditional on meeting the documented threshold and invite the customer to estimate eligible spend before applying.

Use `scripts/rank_promotions.py` for deterministic date, eligibility, and value ranking after extracting the supplied documents into its input schema. The executor must still faithfully extract all terms and formulate the customer-facing answer.

## Customer-facing response checklist

For a customer seeking a personal points/cash bonus, provide a direct answer with:

1. The recommended current documented product and its direct sign-up benefit.
2. The explicit cash redemption value of points, if and only if a supplied document supports a conversion.
3. The exact offer window and full material qualification terms.
4. A statement of whether the customer is known eligible or the recommendation is conditional, including any unknown spend capacity.
5. A concise distinction between relevant expired, invitation-only, or APR-only promotions.
6. A next question focused on whether the customer can meet the required eligible spend in the stated period, if that fact remains unknown.

Use source titles or document identifiers where helpful. Do not fabricate approval, credit limits, offer extensions, merchant qualification, posting timing, redemption options, or benefits absent from the documents.

## No account action in this workflow

General product advice from supplied documents does not require account lookup or identity verification. Do not access customer records merely to compare offers.

If the customer changes the request into a banking action, follow the applicable tool and authorization process. Preserve this mandatory prerequisite verbatim with that resulting procedure:

> Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Promotion-ranking script

Run `scripts/rank_promotions.py` with one JSON object on stdin. It emits one JSON object on stdout and uses only the Python standard library.

### Input schema

```json
{
  "current_date": "YYYY-MM-DD",
  "customer": {
    "new_customer": true,
    "has_invitation": false
  },
  "target_benefit_kinds": ["points", "cash_back", "statement_credit"],
  "offers": [
    {
      "id": "source-document-id-or-key",
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
      "notes": ["Documented condition or exclusion"]
    }
  ]
}
```

Use `cash_value_usd` in `benefit` for a direct documented cash/credit value. For points, include `point_value_usd` only when a source explicitly documents that conversion. Missing customer fields are treated as unknown. Do not put an offer into a current-offer claim if its opening dates are not documented.

### Output and validation

On valid input, the script returns `ok: true` and:

- `ranked_candidates`: active targeted offers that are eligible or conditional, with eligible offers first and then known cash value descending.
- `active_nontargeted`: active offers whose benefit kind is outside the customer's requested benefit kinds, such as APR or fee promotions.
- `excluded`: inactive, date-unknown, or ineligible offers and their reason.

Each item includes date status, eligibility status, requirements that are unknown or failed, and a normalized cash value only where calculable from documented input. If `ok` is false, correct the extraction errors from the source documents rather than guessing.

Runnable call shape (replace all illustrative values with values extracted from the current task documents):

```sh
python scripts/rank_promotions.py <<'JSON'
{"current_date":"YYYY-MM-DD","customer":{},"target_benefit_kinds":["points","cash_back","statement_credit"],"offers":[]}
JSON
```

Before relying on the result, confirm that a recommended item is active, targets the requested benefit type, has no failed requirement, and has a documented conversion if a cash equivalent is stated.
