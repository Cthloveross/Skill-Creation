---
name: travel-and-high-access-account-recommendation
description: Provide a careful, evidence-grounded recommendation for a customer choosing checking and savings accounts, particularly where international ATM use, foreign-currency purchases, balance-dependent fees, savings APY, and frequent withdrawals must be reconciled. Use when the available product facts and a conversation-derived customer profile are supplied.
---

# Travel and high-access account recommendation

## Purpose

Turn a customer's stated banking priorities into a direct recommendation without hiding material fees, qualification thresholds, limitations, or uncertainty. This Skill is designed for advisory conversations only: it does not open accounts, alter customer data, or cause any bank action.

The product facts available for this task are summarized in `references/product_catalog.json`. They are evidence-bound: do not infer an unlisted benefit, waive a fee, or resolve contradictory disclosures in the customer's favor.

## Required inputs

Read the opening message and all completed clarifications before answering. Extract, at minimum:

- whether the customer already holds a checking account and which one;
- international-travel, foreign-currency-purchase, and ATM-use needs;
- likely checking balance and whether the customer can maintain a stated *daily* balance;
- likely savings balance;
- approximate monthly savings withdrawal frequency; and
- the customer's priorities (for example, no foreign transaction fee, reimbursements, yield, or avoiding access fees).

Do **not** request identity verification and do not call account or customer-data tools for a general product recommendation. Do not claim that accounts were opened or that an application was submitted.

## Method

1. **Recommend only from documented facts.** Match the profile against eligibility and fees. A customer's statement that they can keep “three to four thousand” does not establish that they will meet a $3,750 *minimum daily* balance every day. Frame such a recommendation as conditional where appropriate.
2. **Separate distinct ATM and FX costs.** In particular, distinguish:
   - a foreign transaction fee;
   - an account's foreign ATM withdrawal fee;
   - an out-of-network ATM fee charged by the bank;
   - a third-party ATM operator surcharge; and
   - currency conversion markup or merchant/ATM dynamic currency conversion.
   A rebate of operator surcharges is not evidence that the bank's own out-of-network fee is rebated.
3. **Estimate savings access costs from the high end of the stated usage range.** Count the number of withdrawals exceeding the free allowance and multiply by the documented per-withdrawal fee. State that an estimate changes with actual transaction classification and count.
4. **Check balance eligibility separately from yield.** Do not recommend an account with a minimum the customer cannot reasonably meet merely because it advertises a higher APY. State opening minimum, ongoing threshold, and below-threshold fee when documented.
5. **Apply linked-checking APY boosts only when the exact pairing is documented.** Existing checking boosts do not stack with other checking boosts. Do not claim an unspecified relationship or card bonus applies.
6. **Give a clear conclusion, then the caveats.** The customer asked for a recommendation rather than a broad menu. Name the best documented fit and, where important, explain why an apparent alternative is weaker.

`references/product_catalog.json` records a material Purple checking disclosure conflict: it lists a $0 foreign ATM withdrawal fee, while a separate disclosure imposes $2.50 for every out-of-network ATM withdrawal and contains no international exception. Preserve both facts. Explain that the $0 item does not safely eliminate the documented out-of-network fee; it is prudent to expect the $2.50 bank fee at out-of-network ATMs unless the bank confirms otherwise.

## Expected response structure

Use plain, customer-friendly prose with these components:

1. A concise recommendation for checking and savings.
2. A checking explanation covering foreign transaction fee, relevant monthly-fee waiver, ATM surcharge rebate cap, conversion markup, and the out-of-network-fee limitation.
3. A savings explanation covering likely APY tier, balance requirement, free-withdrawal allowance, and likely excess-withdrawal cost.
4. A short comparison to any especially plausible alternative (for example, an account that has a linked APY boost but fewer free withdrawals).
5. A practical next step, such as keeping ATM receipts, selecting local currency rather than optional dynamic currency conversion, monitoring monthly rebate and withdrawal counts, or confirming an ambiguous ATM fee before relying on it.

Use precise currency and percentage units. Say “up to $30 per month” rather than implying unlimited reimbursements. Do not say ATM surcharges are guaranteed to be reimbursed if eligibility conditions are undocumented.

## This task's profile-driven conclusion

When the supplied conversation establishes all of the following:

- frequent international travel and foreign-currency purchases;
- a desire to avoid foreign transaction fees;
- potential ability, but not certainty, to hold at least $3,750 daily in travel checking;
- roughly $5,000–$7,000 in savings; and
- roughly 12–16 or more savings withdrawals per month,

the evidence-supported advice is:

- **Purple Account checking, conditionally**, for the documented 0% foreign transaction fee and up-to-$30 monthly eligible ATM operator-fee rebates, provided the customer can maintain the $3,750 minimum daily balance to avoid its $15 monthly fee. It also has a 0.5% conversion markup. Disclose that third-party fees are separate and that the $2.50 out-of-network withdrawal fee may still apply even abroad despite the separate $0 foreign-ATM-fee statement.
- **Silver Plus savings** as the better access-oriented documented fit, because its $2,500 ongoing requirement is within that balance range, it has 15 free withdrawals monthly, excess withdrawals may cost $1 each, and its balance is below the $15,000 Tier 2 threshold, so its documented base tier is 3.0% APY. Its $1,000 opening requirement and $8 monthly fee below $2,500 must be stated.

Do not present that conclusion as appropriate if a later answer changes any of those premises. In particular, if the customer cannot maintain the Purple daily threshold, state the $15 monthly cost plainly rather than representing Purple as fee-free.

A customer with existing Green checking could receive the documented +0.25% Green-to-Silver boost on Silver savings, but at balances below $10,000 Silver's 2.5% Tier 1 base would be 2.75% with that documented boost. It includes only 10 free monthly withdrawals and $2 per excess withdrawal. For a 12–16 withdrawal pattern, that is ordinarily a less suitable access tradeoff than Silver Plus; calculate the customer-specific excess count rather than asserting a fixed charge. Do not assume the optional 0.025% relationship bonus or credit-card benefits unless the requirements are expressly established.

## Optional calculation helper

Use `scripts/analyze_account_options.py` when a structured profile and product-option records are available. It reads one JSON object from standard input and writes one JSON object to standard output. It provides comparisons and flags; the executor must still write the customer-facing recommendation and disclose ambiguities.

### Input schema

```json
{
  "profile": {
    "checking_balance_low": 0,
    "checking_balance_high": 0,
    "savings_balance_low": 0,
    "savings_balance_high": 0,
    "monthly_withdrawals_low": 0,
    "monthly_withdrawals_high": 0,
    "existing_checking": "optional product name",
    "wants_no_foreign_transaction_fee": true
  },
  "checking_options": [{"name": "...", "foreign_transaction_fee_pct": 0, "monthly_fee": 0, "waiver_min_daily_balance": 0, "operator_rebate_cap": 0, "conversion_markup_pct": 0, "out_of_network_atm_fee": 0}],
  "savings_options": [{"name": "...", "opening_min": 0, "ongoing_min": 0, "monthly_fee_below_min": 0, "free_withdrawals": 0, "excess_withdrawal_fee": 0, "tier1_apy": 0, "tier2_threshold": 0, "tier2_apy": 0, "linked_boosts": {}}]
}
```

All monetary and percentage values are numeric. Omit unavailable values or use `null`; the script will preserve uncertainty rather than treating it as zero.

### Output validation

Before using the result, confirm that:

- `checking[].waiver_status` is not `cannot_meet` for a supposedly fee-waived recommendation;
- `savings[].ongoing_balance_status` is `meets_low_estimate` or is explicitly explained;
- estimated excess withdrawals equal `max(0, stated withdrawals - free withdrawals)` for both range endpoints; and
- `linked_boost_pct` is present only for an explicitly matching existing checking name.

The script never decides that a disclosed contradiction is resolved. Include every such caveat from the source record in the final response.
