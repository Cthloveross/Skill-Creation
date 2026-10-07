---
name: referral-portfolio-optimizer
description: Evaluate and rank checking-account referral options for multiple personal or business prospects while enforcing referrer eligibility first, annual program caps, the shared rolling 9-day bonus limit, account-specific qualification rules, and any active recommendation-priority notice. Use for requests to maximize or compare referral bonuses, plan referral timing, or explain why a referral is conditional or unavailable.
---

# Referral Portfolio Optimizer

Use this Skill to give accurate, conditional referral recommendations without creating referrals or opening accounts.

## Required process

1. **Verify the referrer before discussing referral terms or recommendations.** Confirm the referrer is an eligible Rho-Bank checking customer and obtain either:
   - a confirmed referral-eligibility result from the servicing system, or
   - their first checking-account opening date, so tenure can be compared with the target program.

   Tenure is measured from the **earliest** Rho-Bank checking account opening, not the current account type. A referrer may refer to a different account type. Do not treat prior referral history alone as proof that the customer currently has an eligible checking relationship.

2. Retrieve complete referral history and the current timestamp. Count only `COMPLETE` referrals for per-calendar-year program caps. Check successful-bonus timestamps precisely for the shared cap of two bonuses in any rolling nine-day period. If the available history only has dates, disclose that it cannot establish exact timestamp boundaries.

3. Collect each prospect's facts. At minimum collect personal/business type and intended new-money deposit. Also collect age for age-restricted personal products; for businesses, formation age and whether enterprise status applies where relevant. Confirm the general eligibility restrictions before stating a referral will succeed:
   - the prospect is a new Rho-Bank customer, with no current account and no account closed in the last 12 months;
   - personal prospects have a different registered address from the referrer;
   - business prospects have a primary owner (primary authorized signer SSN) distinct from every existing Rho-Bank business account;
   - no other new-account promotion/sign-up bonus is being combined, and only one referral code will be used;
   - the qualifying deposit is new money, not a transfer from another Rho-Bank account.

4. Run `scripts/referral_optimizer.py` on a runtime JSON case file. The program catalog is in `references/referral_programs.json`. Do not alter the catalog to fit an individual case.

5. Do not call referral, account-opening, or banking-action tools based only on this analysis. If the user wishes to proceed, provide the appropriate referral-link/dashboard or relationship-manager path after all conditions are confirmed.

## Script interface

Run:

```text
python scripts/referral_optimizer.py < case.json
```

The script reads one JSON object from stdin and emits one JSON object to stdout.

### Input schema

```json
{
  "as_of": "ISO-8601 timestamp or YYYY-MM-DD",
  "referrer": {
    "referral_eligibility_confirmed": true,
    "first_checking_opened": "YYYY-MM-DD or null",
    "referrals": [
      {
        "referred_account_type": "official account name",
        "referral_status": "COMPLETE",
        "date": "ISO-8601 timestamp or YYYY-MM-DD"
      }
    ],
    "successful_bonus_timestamps": ["ISO-8601 timestamp"]
  },
  "candidates": [
    {
      "name": "prospect label",
      "kind": "personal or business",
      "deposit": 0,
      "age": 0,
      "business_age_years": 0,
      "enterprise": false,
      "new_customer": true,
      "different_address": true,
      "different_primary_owner": true,
      "no_other_promotion": true,
      "one_referral_code": true,
      "opening_eligibility_confirmed": true
    }
  ]
}
```

`age` applies to personal candidates; `business_age_years` and `enterprise` apply to business candidates. Fields not known may be omitted or set to `null`. The script marks resulting options as `conditional` rather than assuming omitted facts. `different_address` is irrelevant for a business prospect, and `different_primary_owner` is irrelevant for a personal prospect.

`referral_eligibility_confirmed` is the preferred explicit gate. If it is not `true`, the script can use `first_checking_opened` for programs with a documented tenure threshold, but the executor must still confirm that the referrer is currently eligible before communicating any account recommendation. Supply `successful_bonus_timestamps` when available; referral `date` values are only a fallback and are reported as date-level precision.

### Output interpretation and validation

The output has:

- `referrer_gate`: hard-stop eligibility findings and missing evidence;
- `rolling_9_day_limit`: current successful-bonus count, remaining slots, and timestamp precision;
- `candidates[*].options`: ranked account options with bonus totals, annual-cap usage, and blockers/conditions;
- `recommended_option`: the first option that is fully supported by supplied facts, or `null`;
- `timing`: a warning that no more than two successful bonuses may occur in a rolling nine-day interval.

Treat `ineligible` options as unavailable. Treat `conditional` options as possibilities only: state every condition listed and ask for confirmation. Only present `eligible` options as recommendations, and only when `referrer_gate.can_discuss_recommendations` is true. A `null` recommendation does not mean no product exists; it means additional facts or referrer verification are needed.

For each selected option, explain the required deposit and deadline, both bonus amounts, annual capacity, general new-money/retention conditions, good-standing requirement, and possible clawback if the referred account closes within 90 days. Deposits must remain for at least 30 days after the qualification period ends. Do not promise a bonus: bonuses are subject to qualification and may be reversed.

## Ranking rules

The script ranks by confirmed eligibility, then active business-account promotion priority, then combined referrer-plus-new-member bonus. During the documented November 1–30, 2025 business promotion, Sky Blue is prioritized first and Lime Green second whenever they meet all stated requirements; other business accounts are considered only if neither promotional account meets the prospect's requirements. Outside that window, business programs are ranked by combined bonus.

Program rules whose source does not state a qualifying-deposit or tenure number are retained as `null`; the Skill will not invent a number. A null requirement is not a reason to claim the requirement is zero.

## Failure handling

- If `as_of`, a candidate name/kind, or a nonnegative numeric deposit is missing, the script returns `status: "error"` with validation messages.
- If referrer eligibility cannot be confirmed, stop after requesting/obtaining it; do not provide referral terms or recommendations.
- If candidate new-customer, address, ownership, promotional-offer, or opening-eligibility facts are unavailable, give only conditional results and identify the specific missing fact.
- If the annual cap is reached, do not suggest that program. If the rolling cap is reached, do not suggest attempting another qualifying referral until a successful bonus ages out; use exact timestamps where available.
- If there is no evidence that a product supports a requested requirement, say it is unsupported rather than inferring eligibility.
