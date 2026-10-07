---
name: evidence-based-bank-account-recommendations
version: 1.1.0
description: Select and explain one best-fit checking account and one best-fit savings account from current bank-product evidence, disclose material fees and limits, and safely transition to opening only after a later explicit request and verified eligibility.
---

# Evidence-Based Bank Account Recommendations

Use this Skill when a customer asks which personal checking and/or savings account best fits stated needs. It is designed for customers who want the bank to make a focused choice rather than compare a list of products.

## Core rules

1. Treat the current conversation and supplied product documents as available evidence. Do not say product terms are unavailable, and do not transfer the customer merely because a recommendation requires comparing supplied terms.
2. A recommendation is informational, not an account-opening instruction. General statements such as “I’ll sign up for what you recommend” do **not** authorize opening, profile lookup, funding, or transfers.
3. When the customer asks for one checking and one savings choice, lead with exactly one recommendation for each applicable account type. Do not make the customer select from alternatives.
4. Support every product claim with current evidence. Do not promise a fee waiver, APY tier, rebate, bonus, or eligibility result unless its conditions are documented and met by the stated facts.
5. If no product completely satisfies the customer's needs, recommend the closest documented fit and explicitly identify the unmet need. Do not describe a tradeoff as fee-free, unlimited, or guaranteed when it is not.

## Gather only material requirements

Use facts already supplied in the conversation. Ask a clarification only when it is necessary to choose responsibly. Capture:

- **Checking:** expected balance range; foreign card-purchase use; foreign and domestic ATM use; need for ATM fee support; tolerance for recurring fees; and relevant cash-access limits.
- **Savings:** expected balance range; opening-deposit budget; minimum desired APY; compounding preference; expected monthly withdrawals/transfers, including the upper end if usage varies; and whether liquidity or yield is the higher priority.
- **Opening intent:** a later explicit request to open a named account, funding preference, and identification needed for verification.

A customer's statement that they have an account is not proof that it is active, owned by them, old enough for eligibility, or in good standing.

## Compare the current evidence

Create a small factual record for each plausible candidate. Preserve each account's official name.

### Checking fields

Capture foreign-transaction fee, bank foreign-ATM fee, out-of-network ATM fee, separate operator-fee treatment, ATM-rebate cap and eligibility conditions, monthly maintenance fee, waiver threshold, opening/balance requirements, and material daily limits.

For a customer who travels internationally, give substantial weight to a documented zero foreign-transaction fee, a documented zero **bank** foreign-ATM withdrawal fee, and useful operator-fee rebates. A rebate cap is not unlimited reimbursement. An out-of-network fee is a separate disclosure and must not be hidden by a general foreign-ATM benefit.

If the customer's possible balance is below a maintenance-fee waiver threshold, state both the recurring fee and the threshold. Say the fee may apply; do not say it will be waived throughout their stated range.

### Savings fields

Capture opening deposit, ongoing minimum balance, all APY tiers and thresholds, compounding frequency, free withdrawal allowance, documented excess-withdrawal fee, ATM-fee support, and material conditions.

Evaluate the APY at the conservative end of the customer's expected balance, not at an aspirational higher tier. Compare the customer's maximum expected monthly withdrawal/transfer count to the free allowance. If their use can exceed the allowance, disclose the excess fee when documented, or say that the charge is subject to the fee schedule when only that qualification is documented.

Do not assume relationship, linked-checking, or card bonuses. Include them only when the evidence permits them and the customer’s eligibility is verified.

## Make the recommendation

Once sufficient facts are known, respond directly rather than requesting profile information or offering escalation. Use this structure:

1. **Checking — [official account name].** State why it best matches the travel, foreign-purchase, ATM, and balance needs. Include the applicable foreign-transaction fee, bank foreign-ATM fee, operator-fee/rebate cap, and all material monthly-fee and balance-waiver terms. Distinguish the bank's fee from an ATM operator surcharge and any separately documented out-of-network fee.
2. **Savings — [official account name].** State why it is the best documented fit at the customer’s expected balance. Include the opening deposit, ongoing minimum, APY that applies at that balance, compounding, free monthly withdrawal count, higher-tier threshold, and any material excess-withdrawal consequence.
3. **Bottom line.** If either choice has a shortfall—such as a balance range that may trigger a maintenance fee or withdrawals that can exceed the free allowance—say so plainly. The savings recommendation can be the closest fit even if it does not meet a preference for unlimited fee-free access.
4. End by offering to begin the opening process only if the customer wants to proceed. Do not imply that an account has been opened or that the customer is eligible.

Use `scripts/account_fit.py` when structured candidates are available. It is advisory only; review the source evidence and its disclosure flags before responding.

## Action boundary and later opening workflow

Do not use account-opening, funding, transfer, profile-change, or account-retrieval capabilities while the customer is only seeking a recommendation. If the customer subsequently makes a clear request to open a specified account, verify identity, authority, account ownership, product eligibility, available funds, fees, limits, cutoffs, and final confirmation before any banking action.

For a later personal-checking opening, verify the customer, age requirement, checking-account-count limit, closure-history condition, and exact official account selection required by the current procedure. For a later personal-savings opening, verify the customer, an active qualifying checking account and required tenure, savings-account-count limit, account standing, and the exact official account selection. Retrieve account records only after identity verification where required by the runtime procedure.

Before opening, restate the selected account, opening-deposit requirement, ongoing fee or balance conditions, and funding choice, then obtain explicit confirmation. Before an internal funding transfer, separately obtain transfer authorization and verify both account statuses, common ownership, distinct valid account IDs, a positive amount, and sufficient available source funds. If any prerequisite is missing or fails, do not open or transfer funds; explain what is needed.

## Script interface

Run with `python scripts/account_fit.py`. The script reads one JSON object from stdin and emits one JSON object on stdout. It performs no network access and no banking action.

Input schema:

```json
{
  "checking_needs": {
    "expected_balance_min": 0,
    "expected_balance_max": 0,
    "requires_zero_foreign_transaction_fee": false,
    "requires_zero_foreign_atm_fee": false,
    "minimum_atm_rebate": 0
  },
  "savings_needs": {
    "expected_balance_min": 0,
    "expected_balance_max": 0,
    "minimum_apy": 0,
    "withdrawals_per_month_min": 0,
    "withdrawals_per_month_max": 0
  },
  "checking_candidates": [{
    "name": "Official Account Name",
    "foreign_transaction_fee_percent": 0,
    "foreign_atm_fee": 0,
    "out_of_network_atm_fee": 0,
    "atm_rebate_cap": 0,
    "monthly_fee": 0,
    "fee_waiver_balance": 0
  }],
  "savings_candidates": [{
    "name": "Official Account Name",
    "opening_deposit": 0,
    "ongoing_minimum_balance": 0,
    "free_withdrawals_per_month": 0,
    "excess_withdrawal_fee": 0,
    "apy_tiers": [{"minimum_balance": 0, "apy": 0}]
  }]
}
```

All financial values are numeric and percentages are represented as percentage points. Use `null` for an unavailable documented value. The output ranks candidates, identifies constraints that are not met, and lists required customer-facing disclosures. A missing field is not evidence that a favorable term applies.
