---
name: business-referral-bonus-advisor
description: Assess a business-checking referral program and recommend the highest documented referrer bonus compatible with a prospective business's intended deposit and eligibility facts. Use for informational referral questions only; do not use to submit referrals, open accounts, or move funds.
---

# Business Referral Bonus Advisor

Provide a direct, evidence-based recommendation once the needed read-only checks and customer answers are available. This Skill is informational: it neither submits a referral nor guarantees a bonus.

## Scope and safety

- Do **not** open an account, submit a referral, change customer data, or make a payment.
- Use read-only customer and referral-history tools only when they are available and relevant.
- Do not expose unneeded personal data obtained from a lookup.
- Treat customer statements about the prospective business as attestations, not independently verified facts. Clearly state remaining program conditions without unnecessarily withholding an otherwise supported recommendation.
- If a later workflow performs a banking action, preserve this prerequisite verbatim with its procedure:

> Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Required review sequence

1. **Identify the referrer for read-only review.** Obtain a permitted lookup identifier (exact name, user ID, or email), resolve it, and retrieve the referral history using the resolved user ID. Do not treat identity lookup as authority to take an action.
2. **Get the current time.** Use the supplied current-time tool when available.
3. **Establish tenure.** Determine tenure from the earliest checking-account opening date, never from the product being recommended. An authoritative account record is preferred. If the task specifically supplies the customer's answer to a question about their first checking relationship, use that reported duration and say it is customer-reported.
4. **Obtain or use prospective-business facts.** Check whether the business is a new eligible customer with no existing or recently closed account in the program's exclusion period; whether registered addresses differ; and, for business referrals, whether the primary owner/authorized signer differs. Also establish the proposed deposit amount and note requirements concerning new money and other promotions.
5. **Extract each candidate's current documented rules.** Record the product name, referrer reward, required deposit, deposit deadline, referrer-tenure minimum, annual limit and its scope, and any product-opening, retention, good-standing, or clawback terms. Exclude a product whose required qualification terms are not documented rather than inferring them.
6. **Apply referral limits correctly.** Count only statuses that program terms define as successful/paid (normally `COMPLETE`). The rolling cap is cross-product only if the terms say so. A product annual cap is product-specific unless the terms expressly make it global.
7. **Rank and answer.** Rank unblocked documented products by the **referrer's** reward, not the referred business's welcome bonus. Deliver the recommendation in the same response after the available facts have been assessed; do not continue gathering information that has already been supplied.

## Date-only referral records

Referral tools may return dates without times. Do not turn that formatting limitation into a blanket refusal to recommend.

- If every date-only successful referral is plainly before the rolling-window boundary by calendar date, the record establishes that it is outside the window. If all recent counts are plainly below the cap, proceed.
- Obtain exact timestamps only if a date-only record falls on the rolling-window boundary date and could change whether the cap has been reached.
- Do not describe referrals for other products as consuming a product-specific annual cap. State the applicable product count and cap.

Use `scripts/parse_referral_observation.py` for the numbered referral-tool text when useful, then use `scripts/evaluate_referrals.py` for repeatable comparison and limit calculations.

## Calculator

Run:

```text
python scripts/evaluate_referrals.py < input.json
```

The calculator reads one JSON object from stdin and emits one JSON object on stdout. It has no network access and performs no bank action.

### Input schema

```json
{
  "as_of": "ISO timestamp, ISO date, or MM/DD/YYYY tool date",
  "proposed_deposit": 0,
  "referrer_tenure_days": 0,
  "referrals": [
    {
      "date": "ISO timestamp, ISO date, or MM/DD/YYYY",
      "status": "COMPLETE",
      "product_key": "optional stable key",
      "referred_account_type": "optional display name"
    }
  ],
  "shared_rolling_limit": {"max_bonuses": 2, "window_days": 9},
  "eligibility": {
    "new_customer": true,
    "different_address": true,
    "different_primary_owner": true,
    "new_money": null,
    "no_promotion_stacking": null
  },
  "products": [
    {
      "key": "stable key",
      "name": "display name",
      "referrer_bonus": 0,
      "qualifying_deposit": 0,
      "deposit_window_days": 0,
      "min_tenure_days": 0,
      "annual_cap": 0,
      "annual_cap_scope": "product",
      "requires_new_customer": true,
      "requires_different_address": true,
      "requires_different_primary_owner": true,
      "requires_new_money": true,
      "prohibits_promotion_stacking": true
    }
  ]
}
```

Eligibility flags can be `true`, `false`, `null`, or omitted. A required `false` fact is a blocker; missing required facts appear in `unknown_checks` and make an otherwise best option conditional. `annual_cap_scope` is `product` by default and may be `global` only where terms support that. Product matching falls back to normalized account names when referral records lack stable keys.

### Output validation

The output contains `decision` (`eligible`, `conditional`, `blocked`, or `unavailable`), `shared_limit`, `recommendations`, and `evaluated_products`.

Before responding, confirm that:

- `shared_limit.blocked` is false;
- every recommendation has no `blockers`;
- the recommendation has the greatest referrer bonus among unblocked documented products;
- `date_precision_ambiguous` is false, or exact timestamps have been obtained;
- product-specific annual counts use that product's history rather than unrelated referral history; and
- terms not modeled by the calculator (account opening, deposit retention, good standing, payment timing, and clawbacks) are accurately stated from the source material.

## Response requirements

Lead with an unambiguous recommendation, for example in this structure:

1. **Recommendation and reward:** name the best product and the referrer's bonus.
2. **Why it qualifies:** state the proposed-deposit threshold and deadline, plus the referrer's tenure result. Contrast a higher nominal reward only when its documented threshold or another known rule excludes it.
3. **Eligibility result:** state the rolling-limit and relevant annual-cap result, and accurately reflect supplied new-customer, distinct-address, and distinct-owner/signer attestations.
4. **Remaining conditions:** state that the referred business must open the named product, make the qualifying deposit as new money, retain it for the required period where applicable, avoid promotion stacking, and keep required accounts in good standing. Mention documented clawback terms where applicable.

Say that the result is conditional when facts such as new-money source or promotion use remain unconfirmed. Do not call the bonus guaranteed. Do not withhold a supported recommendation merely because a historical date has no timestamp when that date is clearly outside the rolling window.
