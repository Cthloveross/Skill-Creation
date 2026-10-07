---
name: banking-account-fit-and-opening
version: 1.0.0
description: Recommend one best-fit personal checking account and one best-fit personal savings account from supplied bank-product evidence, explain material limits and tradeoffs, and safely handle a subsequent request to open either account.
---

# Banking Account Fit and Opening

Use this Skill when a customer wants a focused recommendation for checking and/or savings accounts, especially where their expected balances, travel usage, APY goals, and withdrawal frequency must be reconciled with product terms. It also covers the safe transition from a recommendation to an account-opening request.

## Scope and evidence discipline

1. Treat the current task's product documents and customer statements as the source of truth. Extract only facts supported there; do not fill gaps with assumptions.
2. Separate three outcomes clearly:
   - **Recommendation:** a non-transactional explanation of the best available fit.
   - **Eligibility assessment:** whether documented opening requirements appear satisfied after verification and account review.
   - **Opening action:** creation of an account. Do not perform this merely because the customer asked for a recommendation or expressed general willingness to sign up.
3. Do not claim that a fee is waived, a rate applies, a rebate is available, or a withdrawal is free unless the relevant product terms support it. State material qualifications, including balance thresholds, caps, operator charges, statement-cycle limits, and terms that are unavailable.
4. When sources appear to distinguish bank fees from third-party/operator fees, explain the distinction. When sources conflict or applicability is unclear, flag that point rather than silently resolving it.
5. If no candidate fully meets the customer's requirements, identify the closest feasible choice and its shortfall. Do not represent it as satisfying an unmet hard requirement.

## Recommendation workflow

### 1. Capture decision-relevant needs

Use the conversation and ask only for missing facts material to the choice. Normalize, where possible:

- Checking: expected balance range; domestic and international ATM use; foreign-transaction use; tolerance for monthly fees; foreign transaction and ATM fee requirements; desired ATM rebates; debit, wire, or deposit needs.
- Savings: expected balance range; opening-deposit budget; minimum acceptable APY; expected monthly withdrawals/transfers (use a range if the customer says "sometimes more"); preference for liquidity versus yield; card or relationship products only if confirmed.
- Opening: whether the customer is requesting an opening now, selected account names, funding preference, and the information needed for identity verification.

A stated existing account is not proof of its active status, ownership, opening date, or eligibility.

### 2. Extract comparable product facts

From the supplied product evidence, make a small candidate record for each relevant product. Preserve the product's official full name and capture only documented fields:

- **Checking:** foreign transaction fee; foreign and out-of-network ATM fees; third-party-fee treatment; ATM-rebate cap and conditions; monthly fee and waiver threshold; applicable balance requirements; deposit requirement; material limits.
- **Savings:** opening deposit; ongoing minimum; APY tiers and thresholds; compounding/payment timing if relevant; free withdrawal allowance and any documented excess-charge qualification; ATM rebates; account-specific eligibility requirements.

A checking account that waives a monthly fee only above a threshold is not “fee-free” for a customer whose stated balance range can fall below that threshold. A savings account's top tier is not applicable unless the customer's anticipated balance reaches its threshold.

### 3. Compare and select

Apply this ordering:

1. Exclude products the customer cannot fund or maintain under documented requirements, unless the customer explicitly says their funds will change.
2. Enforce explicit hard needs first (for example, a required zero foreign transaction fee).
3. For savings, calculate the APY available at the conservative end of the stated balance range and compare the maximum expected monthly withdrawal count with the free allowance.
4. Prefer the candidate with the strongest support for the customer’s highest priorities. A product that misses only an occasional-use limit may still be the best available fit, but that limit must be prominent.
5. Do not stack linked-account, credit-card, relationship, or multiple-checking bonuses unless the documents permit stacking and the customer’s eligibility is confirmed.

For repeatable comparisons, run `scripts/account_fit.py` with facts extracted from the current task. The script ranks structured candidates but does not replace reading the source terms or making an eligibility determination.

### 4. Deliver the customer-facing answer

Lead with exactly one checking recommendation and exactly one savings recommendation when the customer asks for one of each. Keep alternatives out unless needed to disclose a material shortfall or no suitable product exists.

For each recommended account, provide:

- the official product name;
- a concise reason tied to the customer's stated priorities;
- the most important numeric benefits and limitations supported by evidence;
- a clear distinction between a bank charge and any separate third-party charge or rebate cap;
- a practical caveat where their balance or activity may exceed a threshold or free allowance.

Do not fabricate an account-opening result, account number, eligibility status, or funding confirmation. If the customer has only asked for a recommendation, end by asking whether they want to begin the opening process.

## Mandatory controls before any banking action

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

A banking action includes account lookup for an opening decision, opening an account, and moving opening funds. A recommendation alone is not a banking action.

## Account-opening workflow

Run this workflow only after the customer clearly asks to open an account and confirms the exact product selection.

1. **Authenticate and log identity verification.** Locate the customer using an appropriate supplied identifier. Confirm at least two of the four identity fields (date of birth, email, phone number, address) against the record. Obtain the current timestamp and create the required verification record only after the two-field check succeeds. Stop if identity cannot be verified.
2. **Retrieve and inspect accounts.** Use the documented account-retrieval capability for the authenticated customer. Verify account ownership, account status, balances, account classes, and opening dates; do not rely solely on conversation statements.
3. **Check personal checking eligibility before opening checking.** Confirm verified identity, age 18 or older, fewer than four personal checking accounts, no checking account closed for cause in the preceding six months, and the exact desired official account-class name ending in `Account`.
4. **Check personal savings eligibility before opening savings.** Confirm verified identity; at least one active bank checking account held for at least 14 days; fewer than five personal savings accounts; no collections and no negative balances; and the exact desired official account-class name ending in `Account`. A checking account opened today does not itself establish the required 14-day tenure. If the customer already has an eligible checking account, verify that fact from retrieved records.
5. **Obtain a final action confirmation.** State the account(s) to be opened, opening-deposit requirement, any recurring fee/waiver conditions, and funding choice. Obtain explicit authorization for each opening and, separately, for any transfer.
6. **Open only eligible, confirmed accounts.** Use the normal agent account-opening capability documented for the runtime, with `account_type` set correctly and the exact official `account_class`. Never ask the customer to call an internal agent tool.
7. **Arrange savings funding only after opening succeeds.** If the customer authorizes an internal transfer, verify both accounts are ACTIVE or OPEN, have the same owner, have distinct valid account IDs, and the source has sufficient available funds. Validate a positive USD amount, then use the normal internal-transfer capability. If the customer declines, communicate the documented funding deadline and consequence exactly as supported by the product procedure.
8. **Post-action checks.** Verify the account or transfer result, avoid duplicate actions, provide the new-account and funding status, and document the interaction as required.

If a prerequisite is absent or fails, do not open or fund the account. Explain the unmet requirement and, if applicable, the information or future condition needed to proceed.

## Script interface

`python scripts/account_fit.py` reads one JSON object from stdin and emits one JSON object on stdout. It uses no network access and does not execute bank actions.

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
  "checking_candidates": [
    {
      "name": "Official Account Name",
      "foreign_transaction_fee_percent": 0,
      "foreign_atm_fee": 0,
      "atm_rebate_cap": 0,
      "monthly_fee": 0,
      "fee_waiver_balance": 0
    }
  ],
  "savings_candidates": [
    {
      "name": "Official Account Name",
      "opening_deposit": 0,
      "ongoing_minimum_balance": 0,
      "free_withdrawals_per_month": 0,
      "apy_tiers": [{"minimum_balance": 0, "apy": 0}]
    }
  ]
}
```

All monetary and percentage values are JSON numbers; unavailable product facts may be `null`. The output contains ordered `checking` and `savings` evaluations, `best` candidates when supplied, and factual `warnings`. Validate that candidate names are official names from current evidence, review warnings, and ensure the final customer response does not omit a material limitation.
