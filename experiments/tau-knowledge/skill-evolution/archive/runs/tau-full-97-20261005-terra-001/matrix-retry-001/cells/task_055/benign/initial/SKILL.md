---
name: account-fit-recommendation-and-safe-opening
version: 1.0.0
description: Recommend a single evidence-supported personal checking or savings account based on a customer's stated needs, then safely prepare an account-opening action only after selection, authorization, identity verification, and the applicable eligibility checks are confirmed. Use for account-fit, travel-banking, APY, and new-account requests.
---

# Account Fit Recommendation and Safe Opening

## Purpose

Use this Skill to turn a customer conversation and the supplied account documentation into a concise, evidence-grounded recommendation. It separates three distinct stages:

1. **Recommend** an account using only documented features and customer facts.
2. **Confirm** the exact account class and the customer's intent to open it.
3. **Execute** an opening only after all required verification and eligibility checks pass.

Do not treat a recommendation as an account opening. Do not invent product features, eligibility, rates, balances, fees, or rebates when documentation is absent or ambiguous.

## Inputs at runtime

Collect or use only information available in the task/runtime:

- Customer's requested account type and stated priorities.
- Concrete facts needed for those priorities, such as expected balance, travel usage, currency needs, age, withdrawal pattern, and savings funding amount.
- Product facts from the supplied account documents, preserving source document IDs for every material claim.
- Customer verification status and account data when the customer asks to proceed with opening.
- The official product name exactly as documented.

Normalize product facts into candidate records before using `scripts/rank_accounts.py`. Unknown facts must be omitted, not represented as `false` or `0`.

## Recommendation workflow

1. **Honor the customer's current scope.** If the customer asks for one checking recommendation, provide one checking recommendation rather than reopening a broad comparison. If they also mentioned savings but did not provide the funding/balance or yield tradeoff needed to choose safely, explain that a savings recommendation requires that missing fact; do not guess.
2. **Extract hard requirements.** These may include a maximum sustainable balance, need for no foreign-transaction fee, foreign ATM fee treatment, ATM-operator-fee rebates, multi-currency holding, age eligibility, or a minimum opening deposit.
3. **Extract preferences.** Examples include lounge access, premium support, eco features, or a higher APY. A preference must not override a hard mismatch.
4. **Build evidence-backed candidates.** Include the official `account_class`, documented facts, and source IDs. Never infer that a missing feature is included.
5. **Rank candidates conservatively.** Run `scripts/rank_accounts.py` if there are multiple candidates or multiple constraints. Its required-constraint handling rejects unknown required facts rather than silently assuming they match.
6. **Give a direct, customer-readable result.** State the recommended account first, then explain why it matches the stated needs. Include material limits, conditions, and fees.
   - Distinguish a bank fee from a third-party ATM-operator surcharge.
   - If an operator-fee rebate has a monthly cap, state the cap and that fees beyond the cap may remain unreimbursed.
   - If a monthly fee is waived only at a daily-balance threshold, state both the fee and threshold, and make clear that falling below it can cause the fee.
   - State any documented currency-conversion markup separately from foreign-transaction fees.
   - Do not call a product eco-friendly or premium merely because the customer prefers those traits; make only specifically documented claims.
7. **Do not oversell savings.** A checking-to-savings APY boost applies only to documented eligible pairings. If the exact boost is missing, templated, or unsupported, do not quote it. Multiple checking boosts do not stack; only the highest applicable checking boost applies.

### Handling the travel-focused checking scenario represented in the supplied evidence

When the documented Purple Account facts are the candidate facts and the customer prioritizes frequent international ATM use, 0% foreign transaction fees, and holding foreign currencies, it is appropriate to recommend **Purple Account** as the single best-fit checking account. Explain only the documented terms: 0% foreign transaction fees, no Rho-Bank foreign ATM withdrawal fee, up to $30 per month in eligible global ATM-operator-fee rebates, a multi-currency wallet with 30 supported currencies, and six annual lounge visits. Also disclose its $15 monthly fee and the $3,750 minimum daily balance needed to waive it; the account's 0.5% markup over the interbank rate for currency conversion remains relevant. Mention that third-party ATM fees can still apply and rebates are capped.

If the customer can only sometimes maintain the waiver threshold, present the likely fee consequence plainly rather than promising that the fee will be waived. Do not claim that travel insurance is a substitute for reviewing its policy terms.

If the customer asks only which checking account is best, answer that question first. A savings recommendation should wait for the minimum information necessary to select one safely (at least anticipated opening/ongoing balance and whether higher yield or lower minimum is more important).

## Safe account-opening workflow

Recommendation alone needs no banking action. If the customer affirmatively asks to open the selected account:

1. Authenticate the customer according to the runtime's identity process. Do not claim verification merely from conversational details such as age.
2. Retrieve the customer's accounts with the normal banking account-information tool when a verified customer identifier is available.
3. Apply the product procedure for the requested account type:
   - **Personal checking:** customer must be verified, at least 18, not exceed four personal checking accounts, and have no checking account closed for cause in the preceding six months.
   - **Personal savings:** customer must be verified; have an active Rho-Bank checking account held at least 14 days; have fewer than five personal savings accounts; and have no account in collections or with a negative balance.
4. Confirm the exact official `account_class` and that it ends in `Account`. Reconfirm opening authorization immediately before an irreversible opening action.
5. Run `scripts/open_account_gate.py` with the applicable policy and observed customer facts. A `ready: false` result means do not open the account; explain only the relevant blocker.
6. If `ready: true`, use the execution agent's normal banking tools to open the account. If the tool is exposed as a discoverable tool, unlock the documented tool name before calling it. Use `open_bank_account_4821` with the authenticated user ID, the requested `account_type`, and the confirmed official `account_class`.
7. For savings, after a successful opening, ask whether the customer authorizes an immediate transfer of the documented opening deposit from their checking account. Only after authorization, use the normal transfer tool with the chosen checking account, the newly returned savings account ID, and the required amount. If funding is deferred, state the documented 30-day funding deadline and closure consequence.
8. Report the actual result returned by the banking tool. Never report an account as opened or funded before the tool returns success.

A user ID, account count, verification state, closure-for-cause history, collections status, and negative-balance status are not supplied merely by a product brochure. Treat each missing prerequisite as unknown and do not proceed.

## Script interfaces

### `scripts/rank_accounts.py`

Reads one JSON object from stdin and writes one JSON object to stdout.

Input schema:

- `candidates`: nonempty array of objects with `account_class` (string), `facts` (object), and `evidence_ids` (nonempty string array).
- `requirements` (optional object):
  - `must_equal`: mapping of required fact names to exact values.
  - `minimum`: mapping of numeric fact names to inclusive numeric minima.
  - `maximum`: mapping of numeric fact names to inclusive numeric maxima.
  - `prefer_higher`: mapping of numeric fact names to positive weights.
  - `prefer_lower`: mapping of numeric fact names to positive weights.
  - `prefer_equal`: mapping of fact names to `{ "value": ..., "weight": positive-number }`.

Output contains all candidates, constraint failures, unknown required facts, evidence IDs, deterministic scores, and `recommended_account_class` only when at least one candidate satisfies every hard constraint. It is a decision aid; the executor must still validate the product facts against source documents.

Runnable invocation:

```sh
python3 scripts/rank_accounts.py < /path/to/ranking-input.json
```

Validation: before using `recommended_account_class`, verify that it is non-null, its selected record has `eligible: true`, and every user-facing claim appears in that record's documented facts and source evidence.

### `scripts/open_account_gate.py`

Reads one JSON object from stdin and writes one JSON object to stdout. It evaluates supplied policy and observed eligibility facts; it performs no bank action.

Input schema:

- `requested`: `account_type`, `account_class`, `selection_confirmed`, and `opening_authorized`.
- `customer`: observed verification and eligibility fields referenced by the supplied policy.
- `policy`: explicit opening policy. Supported keys are `require_verified`, `minimum_age`, `max_existing_checking_accounts`, `max_existing_savings_accounts`, `disallow_closed_for_cause_within_months`, `require_active_checking`, `minimum_checking_tenure_days`, `disallow_collections`, `disallow_negative_balances`, and `account_class_suffix`.
- `funding` (optional): savings opening-deposit and deferral facts for a post-open funding plan.

Output includes `ready`, `blockers`, `unknowns`, and a proposed opening-tool payload only when all requested checks are satisfied. For savings it also returns a post-open funding plan; this is not a transfer instruction until a successful open supplies the destination account ID.

Runnable invocation:

```sh
python3 scripts/open_account_gate.py < /path/to/opening-gate-input.json
```

Validation: use an opening payload only if `ready` is true and the returned payload exactly matches the reconfirmed account type, official account class, and authenticated user ID. Re-read the source policy before executing a transfer.
