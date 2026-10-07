---
name: savings-apy-recommendation-and-account-change-safety
description: Evaluate the highest supportable savings APY for a stated balance using savings tiers, linked-checking boosts, card and relationship bonuses, and eligibility requirements. Use when a banking customer asks which checking/savings combination maximizes yield, possibly alongside opening or closing accounts.
---

# Savings APY Recommendation and Account-Change Safety

Use this Skill to provide a transparent recommendation without guessing missing rates, eligibility facts, or account terms. It separates an informational APY comparison from any consequential account opening, closing, transfer, or profile action.

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

A name lookup or a customer-provided name alone is not identity verification. For an action, confirm two of the four identity fields (date of birth, email, phone number, and address), retrieve the profile using the appropriate normal banking tool, obtain the current time, and log the successful verification with the normal verification tool.

## Workflow

1. **Determine the requested scope.** A request to identify the best combination is informational. Do not open, close, link, move money, or change an account merely because the customer asks for a recommendation. If the customer also mentioned an account change, first answer the comparison, then request a clear selection and confirmation of each intended action.
2. **Collect authoritative product facts at runtime.** Assemble the supplied product disclosures into the JSON schema documented below. Include every savings product and checking pairing that can plausibly qualify, not just a preferred product. Record exact APY tier rates, opening and ongoing minimums, linked-checking boost amounts, and whether each eligibility condition is known to be met.
3. **Assess eligibility before ranking.** Test the proposed savings funding against both opening and ongoing requirements. Assess checking-account restrictions and funding separately. Verify card, relationship, age, direct-deposit, good-standing, and same-profile requirements where applicable. A bonus with an unknown percentage or unknown eligibility is not a confirmed bonus.
4. **Calculate and rank.** Run `scripts/rank_apy.py`. Linked-checking boosts use the highest applicable boost only; they do not stack. Configure other bonus groups according to their product policy. Never silently add two bonuses from a group that permits only one.
5. **Communicate the result.** State the winning confirmed combination(s), effective APY, relevant base tier, selected bonuses, requirements, and important exclusions. If the script reports `absolute_highest_supported: false`, say that an absolute highest result cannot yet be established and identify the missing fact(s). Do not turn an illustrative APY into a dollar-interest guarantee.
6. **Only after the customer chooses actions, satisfy the banking control.** For a new account, verify identity and authority, product eligibility, required opening funding, account terms/fees/limits, and explicit confirmation. For closure, verify identity, ownership, current available balance, pending activity, any applicable fees/cutoffs, disposition of remaining funds, and explicit confirmation of the particular account being closed. Use only declared normal banking tools.
7. **Handle unavailable actions safely.** If an account closure or other selected action cannot be completed with declared normal banking tools, explain that it cannot be performed in this workflow and, if the customer wants it completed, use the normal human-transfer route with the applicable reason. Do not claim an action was completed when it was only recommended.

## Calculator

Run the packaged helper with JSON on standard input and JSON on standard output:

```sh
python3 scripts/rank_apy.py < input.json
```

The input object has these fields:

- `savings_balance` (required): proposed savings balance as a JSON number or decimal string.
- `savings_products` (required): objects with `name`, either `base_apy` or `apy_tiers`, optional `opening_minimum`, `ongoing_minimum`, and optional `eligibility` (`eligible`, `ineligible`, or `unknown`). A tier has `min_balance`, optional `max_balance`, and `apy`.
- `checking_accounts` (optional): possible checking accounts with `name` and optional `eligibility`. Include resolved product-specific prerequisites in that status.
- `linked_boosts` (optional): objects with `checking`, `savings`, `apy`, and optional `eligibility`. These are automatically treated as a non-stacking highest-only group.
- `other_bonuses` (optional): already-applicable card, relationship, direct-deposit, or tier bonuses. Each has `savings`, `apy`, optional `group` (default `other`), optional `eligibility`, and optional `label`.
- `bonus_policies` (optional): mapping from other-bonus group to `add` or `highest`; groups omitted from this mapping are additive. Use `highest` where product policy permits only the highest bonus.

The result contains `ranked_candidates`, `top_candidates`, `excluded`, `uncertainties`, and `absolute_highest_supported`. APYs are decimal percentage-point strings, preserving exact decimal arithmetic. A candidate without checking is included so an unlinked base rate is compared fairly.

### Validation

Before relying on the result, verify that all candidate savings products were supplied, all APYs and balances are non-negative numeric values, tier ranges cover the stated balance where tiered APY is used, and every included linked boost names an available checking and savings product. The script returns a JSON `errors` array instead of a recommendation for malformed required inputs. Review `uncertainties` and `excluded` even when the script produces a ranking.

## Customer-response checklist

- Do not call a rate “absolute highest” when disclosures omit a potentially applicable boost amount or condition.
- Explain that APY is annualized; actual interest can depend on daily balances, compounding, and the account crediting terms.
- Mention requirements that must remain true for a displayed rate, including same-profile linkage and account good standing.
- If no action is requested after the recommendation, end with a concise invitation to select accounts. If the customer selects accounts, obtain the required verification and explicit confirmations before any banking action.
