---
name: credit-card-signup-bonus-advisor
description: Compare documented credit-card sign-up promotions using the supplied current date and offer materials. Use for an informational recommendation of the largest current documented incentive and a lower-spend alternative; it does not apply cards for a customer or alter an account.
---

# Credit Card Sign-Up Bonus Advisor

Use this skill when a customer asks which credit card has the best sign-up bonus, cash-back bonus, or points bonus.

## Scope and safety

This is an informational product comparison. Do not apply for a card, enroll the customer, redeem rewards, access account details, or make any banking change. Do not state or imply that a customer will be approved, invited, or will receive a bonus.

If a later request asks to take a banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements before acting.

## Required evidence use

Use the current task's supplied offer documents and read-only observations as evidence. A successful current-time observation supplies the as-of date. Do **not** tell the customer that an offer catalog, promotion text, or current materials are unavailable when the task supplies those documents. Do not ask the customer to paste materials that are already present in the task.

Only characterize an offer as current when its documented availability window includes the as-of date, inclusively. An offer whose documented opening deadline or campaign end date precedes the as-of date is expired and must not be presented as current. If an availability window is absent or incomplete, say that current availability is unconfirmed instead of ranking it as current.

Use only facts supported by the supplied materials. State missing conversions, dates, restrictions, or requirements as unknown; never infer them from card tier, reward rate, or ordinary product terms.

## Required response workflow

1. Obtain the as-of date from a supplied successful time observation. If none is supplied, obtain current time through the normal runtime tool before date-sensitive advice.
2. Read all supplied promotion documents and extract, for every candidate promotion:
   - card name and source;
   - offer start and end dates or account-opening deadline;
   - sign-up cash/statement-credit amount or points amount;
   - a documented points redemption value, if any;
   - a documented annual-fee waiver and its standard fee value, if any;
   - eligible-spend threshold and qualification period; and
   - eligibility, invitation, new-customer, good-standing, subscription, and purchase-exclusion conditions.
3. Filter out expired promotions. Normalize a cash or statement credit to its stated USD amount. Normalize points only with a documented USD-per-point conversion. Keep a fee waiver separate from the bonus, while also showing a disclosed combined first-year incentive when useful.
4. Rank availability-confirmed current offers by documented monetary incentive. Do not count normal ongoing earning rates, APR, credit limits, purchase protection, or other non-sign-up product features as a sign-up bonus.
5. Answer directly in the same response. Lead with the card that has the **largest/best/highest documented current sign-up incentive**. Name it explicitly; give its bonus, spend requirement, qualification period, campaign dates, and every material eligibility limitation.
6. Also give a practical lower-spend current alternative when one is documented. State its reward amount and type, documented cash-equivalent value when available, spend requirement and period, end date, and material new-customer/good-standing restrictions.
7. If mentioning an expired card, label it clearly as expired/not current and give the relevant expired deadline. Prefer not to mention expired offers unless that comparison is useful.

For repeated numeric comparison, the executor may run `scripts/rank_signup_offers.py` with facts extracted from the current documents. It is a calculation aid, not evidence: review its output against the source documents and write the customer-facing answer from the documented facts.

## Response requirements

Use this structure, adapting it to the supplied evidence:

- **Best documented current bonus:** Explicitly identify the top card as the best/largest/highest documented current incentive. State the cash/credit or points bonus. If a fee is waived, state the waiver separately and state the fee amount. State qualifying eligible spend, time allowed, and the inclusive campaign window.
- **Who can actually pursue it:** State invitation-only status, score guidance, non-guarantee of invitation, new-customer condition, good-standing condition, or any other documented restriction. A score guideline is not an approval guarantee.
- **Lower-spend current alternative:** Explicitly identify the alternative and explain why it is lower barrier (such as lower required spend), while not calling it the largest bonus. Include its points-to-USD conversion only where documented.
- **Bottom line:** Tie the choice to the customer's stated priority. Explain the spend/eligibility tradeoff concisely.

Cite source document IDs or titles when the interaction format supports citations. Do not make a recommendation contingent on the customer supplying documents if usable materials were supplied in the current task.

## Deterministic ranking helper

### Input

`scripts/rank_signup_offers.py` receives one JSON object on standard input:

```json
{
  "as_of_date": "YYYY-MM-DD",
  "include_availability_unknown": false,
  "offers": [
    {
      "card": "string",
      "source_id": "string",
      "window_start": "YYYY-MM-DD or null",
      "window_end": "YYYY-MM-DD or null",
      "cash_bonus": 0,
      "points_bonus": 0,
      "point_value_usd": 0,
      "fee_waiver_value": 0,
      "required_spend": 0,
      "qualification_months": 0,
      "eligibility_notes": ["string"]
    }
  ]
}
```

Amounts must be nonnegative numbers. `point_value_usd` is the documented USD redemption value per point and must be `null` if it is not documented. Dates must be ISO calendar dates. `source_id` is a document ID or another source label supplied by the current task.

### Output

The script emits JSON with `as_of_date`, `ranked_current_offers`, `excluded_offers`, and `availability_unknown_offers`. Ranked items report separate `cash_bonus`, `points_value_usd`, `fee_waiver_value`, and `total_disclosed_incentive_usd` fields. A points award without a documented conversion is flagged and is not assigned invented dollar value.

Example call pattern, using facts extracted at runtime rather than embedded values:

```text
run_skill_script(
  relative_path="scripts/rank_signup_offers.py",
  input_json={"as_of_date":"...", "offers":[...]}
)
```

## Validation before sending

Check all of the following:

- The response directly names a best documented **current** offer, rather than asking for already-supplied offer material.
- Its campaign dates contain the supplied as-of date.
- The top offer's dollar/point amount, fee waiver, spend threshold, qualification period, and restrictive eligibility terms are all stated accurately.
- A current lower-spend alternative is included when supported, with its conversion, deadline, and new-customer/good-standing terms.
- Expired promotions are omitted or unmistakably labeled expired.
- Fee waivers are not silently conflated with a statement credit, and points are not given a cash value without a documented conversion.
- The answer remains informational and performs no banking action.
