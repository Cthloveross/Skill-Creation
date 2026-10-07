---
name: savings-apy-and-account-replacement-advisor
description: Advise a banking customer on the highest documented savings APY configuration for a stated balance, correctly applying non-stacking card/checking bonus rules, and safely handle a related checking-account closure/replacement request. Use when product terms and available banking tools are supplied.
---

# Savings APY and Account Replacement Advisor

Use this Skill for an informational APY comparison or for the later, separate workflow of closing a checking account and opening a replacement. Do not treat a request for advice as authorization to close, open, apply for a card, transfer funds, or link accounts.

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and safety boundary

1. Separate **information/advice** from **banking actions**.
   - It is safe to explain documented rates, eligibility conditions, and a conditional recommended configuration without identity verification.
   - Opening or closing accounts, applying for or activating cards, linking products, and moving money are banking actions. Obtain verification and an explicit confirmation of the exact action before calling any action tool.
2. Do not state that a customer is eligible for an account or card merely because a product is documented. Treat underwriting, identity/income requirements, subscription requirements, approval, account status, and account-opening rules as conditions unless the relevant requirement has been verified.
3. Never use a name lookup as identity verification. For an action, confirm at least two independent identity fields against the customer record, then call `log_verification` with all requested record fields and a timestamp from `get_current_time`.
4. Do not invent account information. If account lookup/closure/opening tools are not supplied, say that the account facts cannot be checked in the current toolset. Do not infer that a balance is zero, that there are no pending items, or that a customer is eligible from the customer's uncertainty.
5. Do not expose unneeded account identifiers or full personal information in the user-facing explanation or a transfer summary.

## APY calculation method

The advertised APY calculation is an additive percentage-point calculation, not a multiplication of rates:

`effective APY = applicable base/tier APY + highest eligible checking boost + highest eligible card bonus + independently verified relationship/tier bonuses`

Apply these rules exactly:

- Select the savings product's base APY tier using the stated balance and its documented tier threshold.
- Exclude an account from a recommendation when the supplied balance cannot meet its documented ongoing minimum balance. Explain the exclusion rather than implying that a higher headline rate is available on the stated funds.
- If multiple eligible checking accounts offer boosts for the selected savings product, add **only the highest applicable checking boost**.
- If multiple eligible cards offer bonuses for the selected savings product, add **only the highest applicable card bonus**.
- A checking boost and a card bonus may both be added.
- Add a relationship or account-tier bonus only when its qualification has been independently established. Do not assume it just because a customer has a card or another product.
- When documents describe the same card benefit both as a card bonus and as a relationship benefit, treat it as one benefit unless the documents unambiguously establish two distinct, independently qualifying bonuses. Never double-count a disputed classification.
- A theoretical rate is conditional on all product applications, links, and ongoing eligibility succeeding. Explain this before recommending a combination as actionable.

Use `scripts/apy_advisor.py` for repeatable calculations. It calculates only from the runtime JSON supplied to it; it does not look up customers and cannot perform banking actions.

### Script interface

Run `scripts/apy_advisor.py` with JSON on stdin. Required schema:

```json
{
  "balance": 6000,
  "savings_accounts": [
    {
      "id": "unique-savings-id",
      "name": "Product name",
      "minimum_balance": 0,
      "base_apy": 0,
      "tiers": [{"minimum_balance": 0, "apy": 0}],
      "relationship_bonus": {"apy": 0, "qualifies": false}
    }
  ],
  "checking_boosts": [
    {"savings_id": "unique-savings-id", "checking_name": "Product name", "apy": 0}
  ],
  "card_bonuses": [
    {"savings_id": "unique-savings-id", "card_name": "Product name", "apy": 0,
     "eligibility_note": "conditional approval or verified eligibility"}
  ]
}
```

`base_apy` is required when `tiers` is absent. If `tiers` is provided, its applicable tier is the entry with the greatest `minimum_balance` not exceeding `balance`. `relationship_bonus` is optional and is included only with boolean `qualifies: true`. All APY values are percentage points (for example, `0.45`, not `0.0045`). Omit a checking/card entry when its amount is unknown rather than substituting zero.

The script emits JSON with `eligible_configurations`, `best_effective_apy`, `best_configurations`, `excluded_accounts`, and `warnings`. A best result is a maximum only among the supplied documented product records. Read and communicate warnings; if product coverage or required facts are incomplete, call it the best documented result rather than an unconditional global maximum.

## Product facts available in this package

Consult `references/documented_apy_facts.md` to construct runtime input from the applicable public product terms. It contains the sourced rates, thresholds, bonuses, and known eligibility caveats relevant to common Gold, Green, and Silver comparisons. It is not customer-specific and does not establish an applicant's approval or ownership.

For the documented $6,000 comparison represented by those facts, the calculator supports explaining that Silver at its lower 2.5% tier plus the documented EcoCard 2.2% bonus and Bluest checking 0.45% boost is 5.15% APY, conditional on account/card approval, linkage, and continued eligibility. A Green savings configuration can also reach 5.15% only when the Diamond Elite Card bonus is available; the supplied material does not establish its application criteria. Green plus the documented EcoCard is 5.05%. Higher-rate savings products whose ongoing balance minimum exceeds $6,000 must not be presented as maintainable choices for that balance. Do not add an unverified 0.025% relationship bonus.

## User-facing advice flow

1. Restate the balance and clarify that “highest” means the highest **documented, maintainable effective APY**, not a checking-account APY or a rate that requires more funds than the customer has.
2. Calculate the alternatives using the method above. State the arithmetic, the non-stacking selection rule, material minimum balances, and any application/approval conditions.
3. Recommend the best fully quantified, documented configuration. If a tied configuration depends on an undocumented eligibility pathway, present it as conditional rather than replacing the fully documented recommendation.
4. Explain that no accounts, cards, or links have been changed. Ask the customer to choose a precise next step, such as: receive card-application information, open named accounts after eligibility review, or proceed with closing a named old checking account.
5. If the user wants a bank action, follow the action workflow below; do not make a recommendation into consent.

## Account closure and replacement workflow

Use this only after the customer has explicitly requested the action and selected the exact replacement product.

1. Verify identity by confirming two of date of birth, email, phone number, and address against the customer record. Retrieve the current time and log the completed verification.
2. Verify authority and ownership of the old account. Obtain or inspect, using supplied normal banking tools, the account opening date, status, current and available balance, pending transactions, holds, negative/collections status, ownership, and any closure restrictions. Confirm all applicable account-count or recent-closure eligibility requirements for the replacement product.
3. Verify the exact replacement account's product eligibility, required opening deposit, fees, limits, and whether an application/underwriting decision is required. Verify any card's separate eligibility and application requirements; do not imply that opening a deposit account approves a card.
4. Obtain explicit confirmation that names the old account to close, the exact replacement product to open, funding source and amount if applicable, and acceptance of disclosed terms. If the user changed the request to advice, stop here and provide advice instead.
5. Execute only with a supplied ordinary banking tool that supports the requested operation and returns a clear success result. Record the result accurately. Never retry an operation whose result is unknown.
6. If closure functionality is not available, or verified closure conditions cannot be completed, do not claim completion. Offer transfer using `transfer_to_human_agents` with `reason: "account_closure_request"` and a concise summary of the requested closure/replacement and the missing capability or prerequisite. This transfer does not itself close an account.

## Validation checklist

Before responding, verify:

- Every recommended APY uses the correct balance tier and only one card bonus and one checking boost.
- Any other bonus is independently qualified and not a duplicate card benefit.
- Products requiring a higher ongoing balance than the stated funds were excluded or clearly marked unavailable.
- Every card/account recommendation states relevant approval and linkage conditions.
- No banking action occurred based on advice, trust, a name, or an ambiguous preference.
- Before every action, identity, authority, ownership, eligibility, balance/credit, fees, limits, cutoffs, recipient/card details where applicable, and confirmation requirements were verified.
- The response distinguishes documented facts, conditional outcomes, and unavailable data/tools.
