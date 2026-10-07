---
name: banking-account-switch-and-apy-planner
description: Evaluate a customer's requested checking, savings, and credit-card combination; identify the highest supported APY that satisfies stated balance and benefit constraints; and safely execute or stage account-opening and closure requests under Rho-Bank procedures. Use when a customer wants to switch accounts, optimize a savings APY, link products, fund a new savings account, or close a checking account.
---

# Banking Account Switch and APY Planner

Use this Skill to separate (1) a product recommendation from (2) account actions. A mathematically attractive combination is not authorization to open, close, transfer, or apply for a credit card.

## Inputs

Collect or retrieve at runtime:

- Authenticated customer identifier and verification state.
- The customer's requested balance, desired products, and non-rate constraints (for example, early direct deposit, minimum number of early days, travel insurance, and willingness to apply for a card).
- Current bank accounts, including account class, type, status, balance, and opening date.
- Current cards and their status, when card benefits are relevant.
- A product catalog built from the supplied knowledge documents. Represent facts in the schema accepted by `scripts/plan_apy.py`.
- Explicit authorization for each consequential action: opening accounts, closing an account, making a transfer, and beginning a credit-card application.

A name lookup is not identity verification. To verify identity, ask the customer to confirm any two of the four profile fields (date of birth, email, phone number, and address), compare them to the retrieved profile, get the current timestamp, and call `log_verification` with the complete profile values and timestamp.

## Product-analysis method

1. Build the catalog only from documented facts. Do not infer a feature, APY boost, minimum, eligibility rule, or insurance benefit that is not documented.
2. Set `balance` to the amount the customer expects to keep in savings. Treat a savings product as unsuitable when that balance is below a documented opening or ongoing minimum, unless the customer specifically asks to compare products that do not preserve their benefits.
3. For each savings/checking/card combination, add:
   - savings base APY;
   - the highest applicable linked-checking boost only; and
   - the highest applicable credit-card bonus only.
4. A checking boost and a credit-card bonus may be added together. Multiple boosts of the same kind must not be added together.
5. Apply required benefits as hard filters. For example, a card with no documented travel insurance cannot satisfy a travel-insurance requirement merely because it has an APY bonus. Where insurance has an activation condition, disclose it as a condition of the recommendation.
6. Use `scripts/plan_apy.py` to make the selection reproducible. The script does not contain product facts; provide a current evidence-backed catalog on stdin.
7. Present the best supported result, its APY calculation, all material conditions, and any eligibility or approval uncertainties. If a product is only potentially available, say that approval or eligibility must still be confirmed.

### Planner invocation

Run `scripts/plan_apy.py` with JSON on stdin. It emits JSON on stdout.

Input schema:

```json
{
  "savings": [
    {
      "name": "Official savings class ending in Account",
      "base_apy": 0.0,
      "opening_minimum": 0,
      "ongoing_minimum": 0,
      "available": true,
      "eligible": "true|false|unknown"
    }
  ],
  "checking": [
    {
      "name": "Official checking class ending in Account",
      "early_direct_deposit_days": 0,
      "boosts": {"Official savings class ending in Account": 0.0},
      "available": true,
      "eligible": "true|false|unknown"
    }
  ],
  "cards": [
    {
      "name": "Card name",
      "bonuses": {"Official savings class ending in Account": 0.0},
      "travel_insurance": false,
      "travel_coverage_limit": 0,
      "travel_coverage_conditions": ["documented condition"],
      "available": true,
      "eligible": "true|false|unknown"
    }
  ],
  "constraints": {
    "balance": 0,
    "minimum_early_direct_deposit_days": 0,
    "require_travel_insurance": false,
    "minimum_travel_coverage_limit": 0,
    "require_card": false,
    "max_cards": 1,
    "allow_unknown_eligibility": true,
    "require_ongoing_minimum": true
  }
}
```

APY and boost values are percentage-point values (for example, `5.5` and `0.2`), not decimal fractions. Omit a boost mapping when no documented boost exists. An absent early-direct-deposit value is treated as not documented and therefore cannot meet a positive early-deposit requirement. The output includes `recommended`, ranked `alternatives`, rejected-count summaries, and uncertainty flags. Validate that the selected plan meets every `constraints` field before communicating it.

## Safe operational sequence

### 1. Verify and inspect before actions

1. Locate the customer profile, verify two identity fields, and log verification.
2. Unlock and use `get_all_user_accounts_by_user_id_3847` to inspect account type, official class, status, balance, and opening date.
3. Retrieve card accounts when card eligibility, existing bonuses, or product ownership matters.
4. Check the applicable opening rules before opening either account. Do not assume that a recently opened replacement checking account satisfies the savings-account 14-day checking-tenure rule.

### 2. Preserve eligibility while switching

For a customer replacing their only checking account, do not close the existing checking account before proving that the savings opening requirements remain satisfied. In particular, personal savings opening requires an active checking account and at least 14 days of checking tenure. If the existing checking account supplies that tenure, confirm the savings account is opened while the eligible checking relationship remains active, or otherwise wait until a qualifying checking account reaches the required tenure.

Opening a new checking account requires its own eligibility check: verified customer, at least age 18, no more than four personal checking accounts, no checking account closed for cause in the preceding six months, and a confirmed official account-class string ending in `Account`.

Opening personal savings requires: verified customer, an active Rho-Bank checking account, fewer than five personal savings accounts, no account in collections or with a negative balance, and at least 14 days of checking tenure. Use `open_bank_account_4821` only after all applicable checks pass, with `account_type` set to `savings` and the exact official savings account class. The checking opening call likewise requires the exact official checking account class.

### 3. Funding the savings account

Ask whether the customer authorizes an immediate internal transfer and confirm the amount and source checking account. Before an internal transfer, verify both accounts are ACTIVE or OPEN, ownership is the same, the IDs differ, the amount is positive USD, and the source has sufficient funds. Then use `transfer_funds_between_bank_accounts_7291`.

Do not use an internal-transfer tool to simulate an external deposit. If the customer defers funding, communicate the documented 30-day funding deadline and closure consequence. Do not claim a required opening deposit amount unless the product documentation provides one.

### 4. Closing the old checking account

Before closing, establish all documented closure prerequisites: status is OPEN, there are no pending transactions, and the balance is zero unless an applicable early-closure fee can be deducted from the balance. Determine the tier-specific fee and notice period from the old account class and age. A customer statement that an account is “basically empty” does not prove a zero balance or absence of pending transactions.

If the supplied account lookup does not expose pending transactions or another prerequisite, do not call the close tool based on an assumption. Explain the outstanding verification and obtain it through an available approved system or route the closure request to the appropriate human workflow when the prerequisite cannot be verified. Once all requirements are met, use `close_bank_account_7392`.

### 5. Credit-card recommendations and applications

A credit-card recommendation is conditional on the customer meeting the documented application criteria and receiving approval. Explain stated credit-score, subscription, identity, income, and consent requirements. If the runtime provides no agent tool for a credit-card application, do not pretend the card was applied for or opened; direct the customer to the documented application channel after obtaining their decision.

For travel coverage, disclose required activation conditions, coverage caps, exclusions, and documentation requirements. In particular, do not describe an insurance benefit as active merely because the customer holds or plans to apply for a card.

## Customer-facing completion

State separately:

- the recommended product combination and APY arithmetic;
- benefit conditions, including balance requirements and any need to keep accounts/card linked and in good standing;
- whether each requested benefit is documented as met;
- outstanding verification, approval, funding, or authorization items;
- every action actually completed and its funding/closure status.

Never say that a product has been opened, closed, funded, linked, or approved until its relevant banking tool has returned success.

## Failure handling

- **Identity not verified:** stop before account actions; request two profile-field confirmations.
- **Eligibility failure:** do not open the account; state the failed criterion and, where documented, when the customer can qualify.
- **Missing account data or pending-transaction status:** do not close based on incomplete evidence.
- **Insufficient transfer funds or invalid status:** do not transfer; offer a different authorized source or amount after revalidation.
- **No plan meets constraints:** say no documented combination meets all requirements; identify the conflicting hard constraint rather than silently relaxing it.
- **Unknown eligibility or underwriting:** label the recommendation as conditional; do not represent it as approved.

Consult `references/banking_policy_summary.md` for the evidence-backed policy summary used by this Skill.
