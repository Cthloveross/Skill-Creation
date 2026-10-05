---
name: business-referral-recommendation
version: 1.0.0
description: Evaluate which business checking referral program can yield the highest referrer bonus for a proposed deposit, while checking referrer eligibility, referral caps, product thresholds, and global referral restrictions before discussing program terms.
---

# Business Referral Recommendation

Use this Skill for an informational request to compare business checking referral programs or identify the highest potential referrer reward. It does not create a referral, open an account, apply a promotion, or move money.

## Evidence-backed policy scope

The packaged program data covers World Blue, True Blue, Beige, Lime Green, Hunter Green, Cobalt Blue, Navy Blue, and Sky Blue. A product may be listed with incomplete terms when the available evidence does not establish all required qualification criteria. Do not infer missing thresholds.

Across business referral programs:

- The referrer tenure is measured from the earliest Rho-Bank checking account opening date, not the account type currently held.
- A referrer may refer a business to a different checking product than the product they hold.
- The referred business must be new to Rho-Bank, have no existing checking, savings, or account closed within the prior 12 months, use a different registered address from the referrer, and have a primary owner different from every existing Rho-Bank business-account primary owner.
- A qualifying deposit must be new money, not a transfer from another Rho-Bank account, and must remain for at least 30 days after the applicable qualifying period ends.
- Only one referral code applies per new account, and referral bonuses cannot stack with another new-account promotion or sign-up bonus.
- Both accounts must remain in good standing for a bonus to be paid. A bonus may be clawed back if the referred account closes within 90 days of opening.
- No more than two referral bonuses may be received in any rolling nine-day window across all checking account types. A third (or later) referral in that window is denied and cannot be reinstated during that window.

## Required workflow

Perform the following in order. The requirement to check eligibility comes before giving a recommendation, reward amount, or account-specific referral terms.

1. **Identify the customer record.** Ask for an exact account name, email, or user ID. Use the corresponding read-only user lookup. If a name lookup is ambiguous, ask for a unique identifier; do not guess.
2. **Retrieve referral history.** Use `get_referrals_by_user` with the resolved user ID. Record only the fields needed for evaluation: referred account type, status, and completion date. Do not expose unrelated personal data.
3. **Collect or verify eligibility facts before discussing options.** Obtain:
   - the date of the referrer's earliest checking-account opening, or a confirmed tenure sufficient for every potentially relevant program;
   - whether the referrer and referred business accounts are in good standing;
   - whether the referred LLC/business is a new Rho-Bank customer with no qualifying recent prior account;
   - confirmation that addresses differ and that its primary owner differs from owners of existing Rho-Bank business accounts;
   - planned deposit amount and confirmation it will be external new money;
   - confirmation that the business will open the selected product, will not use another new-account offer, and can leave the qualifying funds through the required retention period.
4. **Check current caps.** Count `COMPLETE` referrals in the current calendar year per target product against that product's annual cap. Count all `COMPLETE` referral bonuses dated no more than nine days before the evaluation timestamp across products. If timestamps are unavailable and only dates are supplied, treat a completion dated exactly nine days before the evaluation date as still within the window; disclose that this is conservative.
5. **Evaluate product qualification and choose the highest bonus.** Run `scripts/evaluate_referral_options.py` with normalized, structured information. It reads `references/referral_programs.json`, applies global eligibility, tenure, deposit, annual-cap, and rolling-cap tests, and sorts eligible options by referrer bonus.
6. **Respond accurately.** If all required checks pass, state the highest qualifying product and referrer bonus, then state the specific product deposit/time requirement and material general conditions. Explain why higher-reward products did not qualify when relevant. Make clear that the result is conditional on the actual account opening, qualifying new-money deposit, continued good standing, retention requirement, and no conflicting promotion.
7. **Handle gaps or failures.** If a required fact cannot be confirmed, do not say the customer is eligible and do not disclose product reward comparisons. Ask only for the missing fact(s). If the rolling cap or an annual product cap is reached, say that no additional bonus can be expected under that limit and, for the rolling cap, identify when sufficient time must pass based on the oldest counted completion. If a product’s program data is incomplete, do not recommend it as qualifying.

Do not submit a referral or imply that an informational recommendation reserves a reward. If the customer asks to execute a referral, use only the normal banking workflow and available banking tools after all action prerequisites have been verified; this package has no referral-submission tool.

## Script interface

Run:

```text
python3 scripts/evaluate_referral_options.py < input.json
```

The script receives one JSON object on stdin and emits one JSON object on stdout.

### Input schema

```json
{
  "as_of": "ISO-8601 date or timestamp",
  "proposed_deposit_amount": "decimal amount",
  "referrer": {
    "first_checking_opened": "ISO-8601 date, optional if tenure_days is supplied",
    "tenure_days": "optional integer",
    "account_in_good_standing": true
  },
  "referred_business": {
    "is_new_rho_customer": true,
    "no_existing_or_closed_account_within_12_months": true,
    "different_registered_address": true,
    "different_primary_owner_from_existing_business_accounts": true,
    "account_in_good_standing": true,
    "deposit_is_new_money": true,
    "no_other_new_account_promotion": true,
    "will_open_selected_product": true,
    "can_meet_deposit_retention_requirement": true
  },
  "referrals": [
    {
      "referred_account_type": "product name",
      "referral_status": "COMPLETE",
      "date": "ISO-8601 date or timestamp"
    }
  ]
}
```

`as_of`, `proposed_deposit_amount`, and `referrals` are required. Boolean eligibility fields may be omitted only while the script is being used to identify missing checks. The executor must not share recommendations while `discussion_ready` is `false`.

### Output interpretation and validation

The output includes:

- `discussion_ready`: whether all global eligibility facts necessary to discuss a recommendation were affirmatively confirmed;
- `global_eligibility`: passed, failed, and missing checks;
- `rolling_window`: counted completed bonuses, cap result, and the earliest date at which the present cap clears when determinable;
- `options`: one evaluation per packaged product, including product-specific failures or unknown rules;
- `recommendation`: the best eligible product, or `null` when no product is currently eligible.

Validate before responding that `discussion_ready` is true, `rolling_window.allowed` is true, the selected option is `eligible`, its deposit threshold is no more than the stated planned deposit, its tenure threshold is met, and its calendar-year count is below its cap. If any validation fails, follow the gap/failure handling above instead of presenting a bonus recommendation.

## Mandatory banking-action control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.
