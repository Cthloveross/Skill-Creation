---
name: business-checking-feature-recommendation
description: Recommend a documented business checking account from a customer conversation, explain its relevant fees and benefits accurately, and answer follow-up questions such as ATM rebate availability without making account changes. Use for banking product-selection conversations where product terms and user priorities are supplied.
---

# Business Checking Feature Recommendation

## Purpose
Provide a concise, evidence-grounded recommendation based on the customer's stated non-negotiables and anticipated usage. This Skill is informational: it does not open, convert, close, or otherwise modify an account.

## Required runtime inputs
Read the current conversation and the product facts supplied with the task. Identify:

- the customer's explicit must-haves and preferences;
- balance range and ability to meet a waiver condition;
- payment-card, ATM, mobile-deposit, transfer, transaction-volume, and international needs when known;
- any current account and the precise question in the most recent customer message;
- documented product terms, including qualifications and limits.

Do not infer an unknown feature, eligibility condition, fee, rebate timing, upgrade process, or transaction fee amount.

## Method
1. **Prioritize hard requirements.** Treat an explicit non-negotiable (for example, no bank-assessed overdraft fee) as disqualifying for products that cannot be documented to meet it.
2. **Choose only a supported match.** Recommend an account only when the supplied product documentation supports every stated must-have. A promotion may break ties only when the promoted product independently meets all requirements.
3. **Answer the immediate question first.** If the customer asks about ATM rebates, state the monthly cap, that it is for qualifying out-of-network ATM fees, and the documented posting timing. Do not characterize the cap as unlimited or per transaction.
4. **Connect the answer to the recommendation.** Briefly explain why the account fits the customer using only relevant documented terms (such as waiver threshold, debit-card cashback, card limit, or included transaction allowance).
5. **Use careful conditional language.** For rewards, state that they apply to eligible settled net purchases and can reverse with returns/adjustments. For waiver requirements, say the customer must maintain the documented balance condition; do not guarantee a waiver based solely on a typical balance range.
6. **Give a practical next step.** For ATM questions, suggest retaining receipts and checking activity after the fee posts. If an important requirement remains unknown, ask one focused follow-up question rather than inventing an answer.

## Response structure
Use plain customer-facing language in this order:

1. Direct answer to the latest question.
2. Recommendation and the two to four facts that establish the fit.
3. Important cap, qualification, or uncertainty.
4. A practical monitoring suggestion or one necessary follow-up.

Avoid unnecessary verification, customer-data lookup, account-opening tools, or transfers to a human for a routine product explanation.

## Cobalt Blue reference application
When the supplied evidence identifies Cobalt Blue as the only documented option satisfying a customer's need for no bank-assessed overdraft fees, use `references/cobalt_blue_terms.md`. In particular, distinguish the $15 **monthly** ATM-rebate cap from a promise that every fee will be reimbursed. A customer whose usual balance is above the documented waiver threshold should still be reminded to keep the required balance throughout the applicable period.

## Optional calculation helper
`scripts/estimate_benefits.py` performs deterministic estimates from values explicitly supplied at runtime. It does not select a product and does not replace the documented terms.

Input JSON:
```json
{
  "monthly_eligible_debit_spend": 0,
  "cashback_rate_percent": 0,
  "monthly_atm_fees": 0,
  "monthly_atm_rebate_cap": 0
}
```

All fields are nonnegative numbers in dollars except `cashback_rate_percent`. Output JSON reports gross cashback, the maximum rebate implied by the supplied fee total and cap, and unreimbursed ATM fees. An omitted input is treated as zero. Before using an estimate in a response, confirm that the product documentation supports the eligibility assumptions.

Example runnable call:
```bash
printf '%s' '{"monthly_eligible_debit_spend":3500,"cashback_rate_percent":1,"monthly_atm_fees":18,"monthly_atm_rebate_cap":15}' | python3 scripts/estimate_benefits.py
```

Validate output by confirming that all output dollar values are nonnegative, `estimated_atm_rebate` is no greater than either the supplied fees or the supplied cap, and `estimated_unreimbursed_atm_fees + estimated_atm_rebate` equals the supplied fee total to cents.
