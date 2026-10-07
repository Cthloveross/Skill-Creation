---
name: business-checking-recommendation-and-opening
summary: Compare documented business checking products, recommend a proven match, and—when the customer explicitly requests it—safely open a selected business checking account using only declared banking tools.
description: Use for a customer seeking a business checking recommendation or asking to open a business checking account. Extract hard needs from the dialogue, use supplied product evidence only, disclose tradeoffs, and follow verification, eligibility, confirmation, and result-handling requirements before an opening action. Do not use to invent savings products or perform transfers.
---

# Business Checking Recommendation and Opening

## Scope

Use supplied runtime product evidence and the active dialogue; neither product names nor values in this Skill are product facts. This workflow can give information and, only after an explicit customer request, open a business checking account through a declared banking tool. It cannot infer the availability or terms of business savings, cash deposits, branches, payroll integrations, merchant integrations, or any other feature not documented in supplied evidence.

Never claim that an account is approved, eligible, opened, fee-free, or has a feature unless the evidence or the result of the relevant declared tool supports that claim. Do not make an account action merely because the customer asked for a recommendation.

## Recommendation workflow (informational)

1. Extract requirements from the opening message and clarifications. Treat language such as *must*, *need*, and *non-negotiable* as a hard constraint. Treat an unquantified wish for “more features” as a preference, not a reason to claim an unknown capability.
2. Build a product fact table solely from the supplied evidence. Include documented overdraft policy, monthly fee and waiver condition, transaction allowance, APY, payment fees, deposit/transfer limits, card/user features, and all material limitations relevant to the customer.
3. Exclude a product if evidence says it violates a hard constraint. Also exclude it as a **proven match** when evidence does not establish the hard-constraint value. Do not treat a $0 monthly maintenance fee as proof of no overdraft fee.
4. If several products are proven matches, rank only on documented customer preferences. Apply a time-limited promotional priority only if the supplied evidence establishes that it is active at the current runtime date **and** the promoted product meets every hard constraint. Do not use a promotion to override a hard constraint.
5. Recommend the single best proven match. Explain how it meets each hard requirement, list relevant documented improvements over the current product when known, and disclose material tradeoffs (especially recurring fees, waiver threshold, and relevant transaction fees).
6. Say explicitly when a requested feature or option is not documented. Ask a focused follow-up only when it could change the selection. A customer can still receive a recommendation that satisfies the known hard constraints.
7. End an informational reply by offering further comparison. Explain that opening is separate and requires identity verification, authority, eligibility checks, and the customer's confirmation; do not perform those checks until the customer asks to open an account.

For a zero-overdraft-fee requirement, distinguish a product explicitly documented not to assess overdraft fees from an account with no monthly maintenance fee. Do not recommend a product documented to charge an overdraft fee.

## Optional ranking helper

`scripts/rank_accounts.py` makes documented filtering repeatable. It reads one JSON object from stdin and writes one JSON object to stdout; it makes no banking calls.

Input:

```json
{
  "requirements": {
    "must_equal": {"overdraft_fee": 0},
    "at_least": {"included_transactions": 100},
    "prefer_at_least": {"mobile_deposit_daily_limit": 10000},
    "prefer_true": ["cashback", "multiple_debit_cards"]
  },
  "accounts": [
    {"name": "Name from current evidence", "features": {"overdraft_fee": 0}}
  ]
}
```

All requirement fields and feature fields are optional except `accounts` and each account `name`. Omit undocumented facts rather than setting them to a guessed value. `must_equal` and `at_least` are hard filters; `prefer_*` affects only ranking. Output is `{ "eligible": [...], "excluded": [...] }`, with each exclusion reason. An empty eligible list means no supplied product is a proven match.

Example:

```sh
python3 scripts/rank_accounts.py <<'JSON'
{"requirements":{"must_equal":{"overdraft_fee":0}},"accounts":[{"name":"Example","features":{"overdraft_fee":0}}]}
JSON
```

Before using output in a customer response, validate every input fact against current supplied evidence and independently disclose the documented fees and limits. The helper cannot establish product availability, customer eligibility, or authorization.

## Account-opening workflow (banking action)

Use this section only after the customer expressly asks to open a specific business checking account. A prior recommendation is not consent to open it. Do not use it for a business savings request; product terms and an appropriate opening procedure must be supplied for that separate product.

### Prerequisites and checks

Before the opening call, verify and record all applicable prerequisites:

1. **Explicit selection and confirmation:** confirm the exact account class the customer wants and that they want it opened now. Do not silently substitute a different tier.
2. **Identity:** obtain the customer's full name plus two of these four values: date of birth, email, phone number, or mailing address. Use an appropriate declared lookup tool (`get_user_information_by_name`, `_by_email`, or `_by_id`) to locate the record and compare the provided values with the returned record. Do not use a partial/fuzzy match. If two fields match, call `get_current_time`, then call `log_verification` using the complete returned record and that timestamp. If lookup is ambiguous or a field does not match, stop and request correction; do not log verification or open the account.
3. **Authority and ownership:** obtain the customer's statement that they are authorized to act for the business. Retain the verified customer record as the customer identifier; do not guess a business owner or account owner from a product name.
4. **Product eligibility and account conditions:** apply the supplied opening-policy requirements exactly. For business checking, these may include: verified customer, at least one OPEN personal checking account, no more than six business checking accounts, no CLOSED accounts, and an existing checking balance of at least $500. Check those conditions using a declared read-only capability when one is provided. If the only declared account-record capability is the official opening endpoint, submit no fabricated eligibility result: it performs the system-side eligibility evaluation, and its returned result is authoritative. Never tell the customer they are eligible until it succeeds. Do not bypass or retry a failed or unknown result.
5. **Action details:** verify `user_id`, account type `business_checking`, exact `account_class`, applicable fees/limits/terms, and all confirmation requirements. Available balance, recipient, card, payment, and transfer details are not applicable to an account-opening action; do not fabricate them.

### Execute and report

1. Find the official tool name only when supplied in the current evidence, then unlock it with `unlock_discoverable_agent_tool`. For an opening procedure that specifically supplies `open_bank_account_4821`, unlock that exact tool.
2. Call it once through `call_discoverable_agent_tool` with only its documented JSON arguments: verified `user_id`, `account_type` set to `business_checking`, and the confirmed exact `account_class`. Do not invent parameters or use a shell/script to invoke bank actions.
3. Treat the tool response as the outcome. On success, tell the customer the account is open and report only returned non-sensitive details (such as account class, status, initial balance, and opened date). Do not expose account IDs unless the customer needs one and disclosure is appropriate.
4. On rejection, missing eligibility, or error, do not say the account opened. Explain the returned actionable reason if present, request only missing information or use the permitted escalation path. Never repeat an operation reported as UNKNOWN.

## Unsupported requests

If evidence does not contain business-savings products, do not make up options, rates, withdrawal rules, or an opening process. State that the available information does not establish those details and offer to compare customer-supplied options or route the customer to the appropriate savings-product resource. Do not transfer to a human unless the customer requests one or the declared policy requires it.
