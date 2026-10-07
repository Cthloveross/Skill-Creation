---
name: banking-account-needs-assessment
version: 1.0.0
description: Assess a customer's stated checking and savings needs against a supplied account catalog, ask only decision-relevant follow-up questions, and provide transparent conditional recommendations. Use for read-only account-product guidance; do not use it to open, alter, or transact on an account.
---

# Banking Account Needs Assessment

Use this Skill to guide a customer choosing accounts when product details, trade-offs, linked-account benefits, and the customer's preferences must be considered together. It is designed for advisory conversations, not account servicing or account opening.

## Scope and safety

- Treat product facts supplied in the current task, approved knowledge base, or a runtime catalog as authoritative. Do not invent missing rates, eligibility rules, fees, or features.
- Do not perform or imply an account-opening, linking, enrollment, transfer, card, profile, or other banking action. A recommendation is not an enrollment instruction.
- Do not claim a waiver, rebate, bonus, or APY boost applies until its stated eligibility conditions are confirmed.
- Distinguish bank fees from third-party operator, network, merchant, foreign-exchange, or dynamic-currency-conversion charges.
- If product documentation conflicts, report the conflict and avoid a definitive claim until an authoritative source resolves it.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Workflow

1. **Identify the request type.** Confirm whether the customer wants product guidance, an account action, or both. This Skill covers only guidance. For a later banking action, follow the mandatory control above before taking that action.
2. **Extract known priorities.** Record needs separately for checking and savings. Typical checking priorities include international card use, foreign ATM use, expected ATM frequency, ATM-operator-fee rebates, balance maintained, monthly fee tolerance, currencies received/held, direct deposit, and overdraft preference. Savings priorities include expected balance, access/withdrawal frequency, yield priority, minimum-balance tolerance, and relevant linked products.
3. **Ask the minimum useful questions.** Do not repeat answers already provided. Ask for only information that could change the recommendation. In particular, do not recommend a savings account conclusively without expected savings balance and liquidity/withdrawal preference, unless the catalog makes one option unambiguously suitable under every plausible answer.
4. **Normalize product facts.** For every viable product, capture the monthly fee and waiver condition, balance requirements, relevant transaction limits, transaction/ATM/foreign-exchange fees, rebates and their caps, supported currencies, APY, and relationship or card bonuses. Include conditions, not just headline values.
5. **Evaluate fit by account type.**
   - For travel checking, compare foreign transaction fees, foreign ATM fees, ATM-operator-fee reimbursement caps, wallet/currency support, conversion markup, daily withdrawal limits, and monthly-fee waiver feasibility.
   - For savings, compare base APY, minimum balances, withdrawal limits/fees, liquidity, and only confirmed bonus eligibility.
   - If more than one linked-checking boost could apply, use the catalog’s selection rule. Do not add boosts when the policy says only the highest applies.
6. **State a transparent recommendation.** Give the best fit and a concise reason tied to the customer's priorities. State material costs and conditions, plus one alternative when it is meaningfully better under a different preference. Use conditional wording where facts remain unknown.
7. **Close with the next safe step.** If the customer wants to proceed with opening or linking, explain that eligibility, ownership, fees, balance requirements, and confirmation must be checked through the normal banking workflow before any action.

## Using the helper

`scripts/evaluate_account_fit.py` performs deterministic catalog validation, highlights missing decision inputs, and ranks supplied products using declared preferences. It does not access bank systems and does not execute recommendations.

Run it with JSON on standard input. Example schema (values are illustrative placeholders and must be supplied from the current task):

```json
{
  "customer_needs": {
    "travel_internationally": true,
    "uses_foreign_atms": true,
    "expected_checking_balance": 0,
    "wants_multi_currency_wallet": true,
    "savings_balance": null,
    "savings_priority": null,
    "savings_withdrawals_per_month": null
  },
  "products": [
    {
      "name": "Account name from current catalog",
      "type": "checking",
      "monthly_fee": 0,
      "monthly_fee_waiver_balance": 0,
      "foreign_transaction_fee_percent": 0,
      "foreign_atm_fee": 0,
      "atm_rebate_cap_monthly": 0,
      "wallet_currencies": 0,
      "conversion_markup_percent": null,
      "apy_percent": null,
      "minimum_balance": 0,
      "withdrawals_free_per_month": null,
      "excess_withdrawal_fee": null,
      "linked_boosts": {"Savings account name": 0}
    }
  ],
  "existing_checking_names": [],
  "boost_selection": "highest_only"
}
```

The script emits `{ "status", "missing_inputs", "rankings", "notes" }`. `status` is `needs_clarification` when a requested account type lacks information needed for a defensible recommendation. Use `missing_inputs` to form the next conversational question. Review every `notes` item before responding: it flags incomplete product records and unverified bonus assumptions.

## Response template

1. Acknowledge the specific priorities already stated.
2. Identify the leading checking choice, including the relevant fee/rebate/wallet conditions and any balance needed to avoid a monthly fee.
3. Explain what remains unknown for savings and ask a compact combined question for those missing facts.
4. Do not pressure the customer to enroll. If they ask to enroll, switch to the normal banking workflow and complete the mandatory prerequisites first.
