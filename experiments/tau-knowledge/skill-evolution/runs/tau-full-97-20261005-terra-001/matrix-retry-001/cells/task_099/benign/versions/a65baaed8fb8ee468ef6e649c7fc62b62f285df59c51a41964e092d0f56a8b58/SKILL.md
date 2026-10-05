---
name: business-checking-referral-recommender
description: Verify a checking customer's referral eligibility, compare documented business-checking referral programs to a proposed funding amount, and give the highest supported referrer-bonus recommendation with all material qualification terms. Use for business-account referral questions before any account-opening action.
---

# Business Checking Referral Recommender

## Required workflow

1. **Establish eligibility before giving referral terms or a recommendation.** Identify the referrer, obtain their referral history, and confirm:
   - the referred business is a new Rho-Bank customer with no existing account or account closed in the prior 12 months;
   - the referrer and referred business have different registered addresses;
   - the referred business has a different primary owner from every existing Rho-Bank business account;
   - funding will be qualifying **external new money**, not a transfer from another Rho-Bank account; and
   - the referrer's earliest Rho-Bank checking relationship meets the applicable product tenure threshold. Referrals may cross checking products.
2. Retrieve the current time and evaluate only `COMPLETE` referrals against the shared rolling limit of two successful bonuses in the preceding nine days. A date-only history record is adequate unless it is close enough to the nine-day boundary that its time of day could change the result.
3. Use the documented program table in `references/documented_business_referral_programs.md`. Do not claim that product-specific terms are unavailable when that reference supplies the needed terms.
4. Supply the facts and the relevant documented programs to `scripts/evaluate_referral.py`. This calculation helper performs no banking action and does not submit a referral.
5. Recommend the eligible documented program with the highest **referrer** bonus. A customer confirmation that their earliest account has been open at least the stated threshold is enough for that threshold; do not require an exact opening date. If the confirmation is only “at least 90 days,” it establishes 90 days but not a higher 120-day requirement.
6. Give a direct, customer-readable answer. Do not leave the recommendation pending when the required facts and documented terms establish it.

## Required content of the final recommendation

State all of the following when applicable:

- recommended account and the referrer's bonus;
- why any higher advertised bonus does not fit the stated funding or tenure;
- the recommended account's qualifying deposit amount and funding window;
- that the funding must be external new money and remain in the account for at least 30 days after the qualification period ends;
- one referral offer/code only: the referral bonus **cannot be combined** with another new-account promotion or sign-up bonus;
- both accounts must remain in good standing, and closing the referred account within 90 days may cause a clawback;
- whether the rolling two-successful-bonuses-in-nine-days limit currently permits submission; and
- a documented annual cap or credit timing, if one is documented for the selected product.

For example, if the verified facts show a business can fund about $30,000 externally, the referrer meets the 90-day threshold, and the rolling limit is clear, recommend **World Blue**: its $300 referrer bonus is the highest documented compatible amount. Explain that True Blue's $350 needs $50,000 and Beige's $500 needs $100,000. The referred business must open World Blue and deposit at least $25,000 within 90 days.

Do not treat a recommendation as an account-opening instruction. If the prospect elects to open an account, separately follow the documented opening procedure: verify identity, check opening eligibility, obtain the selected account class, and use the documented account-opening capability only when it is available. Do not invent tool arguments or open an account merely because a referral program was recommended.

## Calculator interface

Run:

```text
python3 scripts/evaluate_referral.py < input.json
```

The script reads one JSON object on stdin and writes one JSON object on stdout.

Input schema:

```json
{
  "current_time": "ISO-8601 timestamp, YYYY-MM-DD, or MM/DD/YYYY",
  "referrals": [
    {
      "referred_account_type": "account label",
      "referral_status": "COMPLETE",
      "date": "timestamp, YYYY-MM-DD, or MM/DD/YYYY"
    }
  ],
  "referrer": {
    "tenure_days": 90
  },
  "prospect": {
    "is_new_customer": true,
    "different_registered_address": true,
    "different_primary_business_owner": true,
    "deposit_is_external_new_money": true,
    "deposit_amount": 30000
  },
  "programs": [
    {
      "id": "world-blue",
      "account_name": "World Blue",
      "account_names": ["World Blue Account"],
      "referrer_bonus": 300,
      "qualifying_deposit": 25000,
      "deposit_window_days": 90,
      "referrer_tenure_days": 90,
      "annual_cap": 12
    }
  ]
}
```

Use a conservative numeric lower bound for `tenure_days`: when a customer confirms “at least 90 days” or “well over 90 days,” `90` is sufficient to evaluate programs requiring 90 days. Do not inflate that statement to 120 days. Product fields that are not documented must be omitted rather than guessed.

The output contains `rolling_limit`, `eligible_programs`, `blocked_programs`, `pending_programs`, and `recommendation`. Before relying on a recommendation, check that `ok` is true, common eligibility has no blocking or pending reasons, `rolling_limit.can_submit_now` is true, and the chosen product is in `eligible_programs`. `COMPLETE` alone counts toward rolling and annual completed-referral limits.
