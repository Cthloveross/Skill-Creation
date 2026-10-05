---
name: business-checking-referral-recommender
description: Determine whether a checking customer may submit a business referral, compare documented business-account referral programs against a proposed external deposit, and give a compliant highest-bonus recommendation with qualification conditions. Use for referral-program questions before recommending an account or helping open one.
---

# Business Checking Referral Recommender

## Required sequence

1. **Check referrer eligibility before discussing or recommending referral terms.** Obtain a customer identifier, retrieve their referral history, and collect or verify the facts needed for the common restrictions:
   - the prospect is new to the bank and has not had a relevant account in the exclusion period;
   - referrer and prospect do not share a registered address;
   - for a business referral, the prospect has a different primary owner from every existing bank business account;
   - the intended qualifying deposit is external new money, not an internal transfer;
   - the referrer has the product's required tenure measured from their *earliest* checking account, not their current product.
2. Obtain the current timestamp and count only successful/`COMPLETE` bonuses in the prior rolling nine-day interval across **all** checking products. If two such bonuses are already in the interval, do not recommend submitting another referral now; explain that it will be denied and identify that the customer must wait until the count drops below two.
3. Assemble one runtime `programs` row per product from the documented product terms. Include the referrer bonus, qualifying deposit, deposit window, tenure, annual cap, and all account-name aliases used in referral history. Do not infer missing product terms.
4. Run `scripts/evaluate_referral.py` with the retrieved history and collected facts. The script is a calculation and consistency aid; it does not query bank systems or submit a referral.
5. Recommend only the highest referrer bonus in the script's `eligible_programs`. Clearly distinguish a verified fact from a customer-provided confirmation. If eligibility or terms are unknown, say what must be confirmed rather than presenting a conditional program as approved.
6. State material conditions retained after the recommendation: the prospect must open the specified account, make the required external-new-money deposit within its window, retain it at least 30 days after the qualifying period ends, both accounts must remain in good standing, no competing new-account promotion or second referral code may be used, and an early closure may trigger a clawback. Mention the applicable annual cap and expected credit timing only when documented for that product.

A referral may cross products: the referrer need not hold the recommended account class. However, neither this fact nor a large advertised bonus overrides that product's deposit threshold, referrer-tenure requirement, annual cap, or the general rolling limit.

## Script interface

Run:

```text
python3 scripts/evaluate_referral.py < input.json
```

The script reads one JSON object from stdin and emits one JSON object to stdout.

Input schema:

```json
{
  "current_time": "ISO-8601 timestamp or YYYY-MM-DD",
  "referrals": [
    {
      "referred_account_type": "product label in history",
      "referral_status": "COMPLETE",
      "date": "timestamp or YYYY-MM-DD"
    }
  ],
  "referrer": {"tenure_days": 0},
  "prospect": {
    "is_new_customer": true,
    "different_registered_address": true,
    "different_primary_business_owner": true,
    "deposit_is_external_new_money": true,
    "deposit_amount": 0
  },
  "programs": [
    {
      "id": "stable product key",
      "account_name": "recommended account name",
      "account_names": ["optional history aliases"],
      "referrer_bonus": 0,
      "qualifying_deposit": 0,
      "deposit_window_days": 0,
      "referrer_tenure_days": 0,
      "annual_cap": 0
    }
  ]
}
```

Use JSON booleans for known common eligibility facts. Omit a fact or use `null` when it is not known. `tenure_confirmed: true` may be used instead of `tenure_days` when only an attestation is available. Amounts are numeric values in a common currency. Program fields that are undocumented should be omitted or null rather than guessed.

Output includes `rolling_limit`, `common_eligibility`, `eligible_programs`, `blocked_programs`, `pending_programs`, and `recommendation`. `recommendation` is null when there is no currently eligible, fully documented product. A date-only referral record is flagged as lower precision only when it lies on the rolling-window boundary; obtain an exact timestamp before treating a boundary case as approved.

## Interpretation and validation

Before relying on the result, confirm that:

- `ok` is true and `errors` is empty;
- `common_eligibility.blocking_reasons` is empty;
- `rolling_limit.can_submit_now` is true and `needs_exact_timestamp` is false;
- the chosen product appears in `eligible_programs`, not merely `pending_programs`;
- the `annual_complete_referrals` count is below that product's cap.

Use the result's `blocking_reasons` and `pending_reasons` verbatim or paraphrased to provide an actionable explanation. Do not equate `APPLIED`, `IN_PROGRESS`, `NO_PROGRESS`, `REJECTED`, or `ERROR` with a received bonus; only `COMPLETE` counts for the general successful-bonus limit and annual completed-referral count used here.

## If the prospect proceeds to opening

Recommendation is not account opening. Follow the documented business-account opening procedure separately: verify the prospective account owner’s identity, check the applicable opening eligibility rules, have them select the account class, then use the documented account-opening tool only if it is available in the execution environment. Identity verification requires confirmation of two of the required identity fields and the corresponding verification log. Do not invent opening-tool arguments, and do not open an account solely because this calculator selected a referral program.

If any required record, product term, identity fact, or ownership comparison cannot be established through the available tools and customer confirmation, leave the referral recommendation pending and explain the specific missing item.