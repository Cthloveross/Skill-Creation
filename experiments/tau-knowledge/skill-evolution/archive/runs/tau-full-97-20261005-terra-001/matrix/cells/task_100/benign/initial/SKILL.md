---
name: business-checking-referral-advisor
description: Evaluate whether a checking customer may submit a business-account referral, compare documented referral programs against planned funding and the customer's goal, and produce a safe, evidence-based recommendation. Use for questions about maximizing a business checking referral bonus or qualifying a referred business.
---

# Business Checking Referral Advisor

Use this Skill before giving a referral recommendation. A recommendation must be gated by the referrer's eligibility, because referral guidance must not be given to someone who cannot submit a referral.

## Required runtime information

Collect or retrieve, without making account or referral changes:

1. Referrer identity and their referral history/statuses, including timestamps of successful bonuses.
2. The date of the referrer's *first* Rho-Bank checking account, not the current account's opening date.
3. Confirmation that the prospective business is represented by a new Rho-Bank customer, has a different registered address, and has a primary owner different from every existing Rho-Bank business account.
4. Planned new-money deposit amount and expected funding timing.
5. For whether the referred business can open an account: whether its owner is verified, has an OPEN personal checking account with at least $500, has no CLOSED accounts, and has fewer than six business checking accounts.
6. The current timestamp, so rolling-window and promotion dates can be evaluated.

Do not treat an unverified assertion as a system confirmation. It can support a conditional answer, but identify it as customer-provided where appropriate.

## Decision procedure

1. **Gate the referral recommendation.** Check all of the following first:
   - the product-specific tenure requirement, measured from the earliest checking account;
   - no more than two successful referral bonuses in the preceding rolling nine days (an event is still in the window through nine days old; an additional referral is safe only after enough time has elapsed to be outside it);
   - the referred customer is new, separate-addressed, and, for a business, has a different primary owner;
   - the product's annual cap, based on successful bonuses in the current calendar year.

   If any required fact is false, say the person is not eligible and explain the applicable restriction. If a required fact is missing, ask only for that fact and do not rank products as a final recommendation.

2. **Separate referral eligibility from account-opening eligibility.** The prospective owner must be verified, have an OPEN personal checking account with at least $500, have no CLOSED accounts, and have fewer than six business accounts before a business checking account can be opened. Unknown opening prerequisites do not establish that the account can be opened. State that they must be confirmed before proceeding.

3. **Compare products only using documented terms.** The funding must be new money (not moved from another Rho-Bank account), meet the product's required amount within its deposit window, and remain in the account at least 30 days after the qualifying period ends. Exclude products whose documented required deposit exceeds planned funding. Do not invent missing qualification terms.

4. **Honor the request's actual priority.** If the customer explicitly seeks the largest referrer bonus, select the highest documented bonus among programs that meet every known requirement. A time-limited promotional ordering applies only when multiple products meet all stated requirements; it does not override an explicit requirement for the largest bonus. If the promotion is active and relevant, disclose that conclusion briefly.

5. **Give complete material terms.** Include the recommended product, referrer reward, planned-deposit comparison, deposit deadline, tenure requirement, annual cap, global rolling cap, payment timing when documented, and key restrictions: one referral code/no stacking, 30-day holding period, good-standing requirement, and possible clawback if the referred account closes within 90 days.

6. **Do not take an action merely because of the analysis.** This Skill makes no referral and opens no account. If a later task asks for either action, use only the normal authorized banking tools after all prerequisites are established.

## Deterministic helper

`scripts/referral_advisor.py` reads JSON from stdin and emits JSON to stdout. It reads the packaged referral catalog and performs repeatable tenure, rolling-window, annual-cap, deposit, and ranking checks.

Input schema (all dates are ISO-8601 date/datetime strings; `Z` is accepted):

```json
{
  "now": "2025-11-14T03:40:00-05:00",
  "planned_new_money_deposit": 31000,
  "referrer": {"first_checking_opened": "2025-07-15"},
  "general_referral_facts": {
    "new_customer": true,
    "separate_registered_address": true,
    "different_business_primary_owner": true
  },
  "successful_bonus_events": [
    {"product": "World Blue", "credited_at": "2025-11-01T10:00:00-05:00"}
  ]
}
```

`successful_bonus_events` must contain only successfully credited/COMPLETE bonuses. Supply `[]` when a referral lookup conclusively shows none; omit the field when history is not known. Boolean facts may be omitted when unknown. The output contains `global_gate`, product-by-product outcomes, ranked fully documented qualifying products, and a recommendation only when known data supports one.

Example runnable invocation by an executor:

```bash
python3 scripts/referral_advisor.py <<'JSON'
{"now":"2025-11-14T03:40:00-05:00","planned_new_money_deposit":31000,"referrer":{"first_checking_opened":"2025-07-15"},"general_referral_facts":{"new_customer":true,"separate_registered_address":true,"different_business_primary_owner":true},"successful_bonus_events":[]}
JSON
```

Validate the result before using it: `global_gate.status` must be `pass`, and the recommendation must be non-null with `eligibility_status` equal to `qualifies_from_known_inputs`. Treat `needs_confirmation`, `blocked`, malformed dates, or `catalog_terms_incomplete` as non-final results. The helper evaluates referral-program eligibility; it deliberately does not claim the prospective business satisfies account-opening prerequisites.

## Source basis

- `references/referral_programs.json`: documented business referral rewards, thresholds, tenure, windows, caps, and source identifiers.
- General referral restrictions: checking-referral program terms and FAQ.
- Account-opening prerequisites: Internal: Opening Business Checking Accounts.
- Promotional ordering: Internal: Business Checking Account Promotion - November 2025.
