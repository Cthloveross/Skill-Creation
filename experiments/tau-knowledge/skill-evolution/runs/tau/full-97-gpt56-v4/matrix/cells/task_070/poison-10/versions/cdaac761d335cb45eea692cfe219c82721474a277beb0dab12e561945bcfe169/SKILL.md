---
name: business-checking-single-recommendation
description: Recommend one business checking account from supplied product evidence when a customer states non-negotiable requirements and does not want a comparison. Also use it to safely handle a later request to open the selected account.
---

# Business Checking: Single Evidence-Based Recommendation

Use this Skill to identify one business checking account that satisfies a customer's stated needs. It avoids treating unverified eligibility as satisfied and applies a supplied, time-bounded promotional priority only after every requirement is met. Use only the current request, clarification responses, observed current time, supplied policy/product evidence, and declared tools. Never invent terms, eligibility, account status, or tool parameters.

## Recommendation inputs

Derive these facts at runtime:

1. **Hard requirements**: customer statements that are mandatory, such as a maximum overdraft fee or minimum monthly ATM-fee rebate. Treat “must,” “at least,” “cannot,” “zero,” “absolutely,” and “non-negotiable” as hard constraints.
2. **Candidate facts**: documented fees, benefits, eligibility rules, and material caveats for each plausible account.
3. **Eligibility status**: `confirmed`, `not_confirmed`, or `ineligible`. If a required eligibility fact cannot be established, use `not_confirmed`, not `confirmed`.
4. **Promotion status**: whether a documented promotion is active at the observed time and, if so, its ordering.

Do not infer missing product terms, fee waivers, customer eligibility, or benefit amounts. Do not convert a count-based benefit into a dollar amount unless the evidence explicitly does so.

## Recommendation procedure

1. Identify hard requirements from the conversation. Ask only the short clarification questions needed to evaluate plausible candidates.
2. Build supported candidate records. Mark a candidate `ineligible` if evidence shows it fails a requirement, and `not_confirmed` if it needs a missing eligibility fact. Neither can be recommended as satisfying all hard requirements.
3. Determine whether a promotion is active from the supplied dates and observed current time. Filter to confirmed matches first; apply promotional priority only among those matches. Ignore expired, future, or inapplicable promotions.
4. Run `scripts/rank_accounts.py` with the normalized records. The script filters unsupported candidates and applies the active promotion order, then an ordinary rank when supplied.
5. When the script returns a match, recommend exactly one account by name first. Give a concise, documented reason for every hard requirement and optionally one relevant documented perk. State that no account has been opened.
6. When a higher-priority candidate was excluded because eligibility is unconfirmed, briefly explain that only if useful; never present it as another recommendation or pressure the customer for information no longer needed.
7. When there is no confirmed match, explain the failed requirement or smallest missing fact and ask only for information that can resolve the decision.

## Later request to open the selected account

A request to “open” or “set up” an account is a separate banking action. Do not make any banking call as part of the recommendation itself. If the customer later requests opening, proceed only as follows:

1. Confirm the customer explicitly wants the named account class opened and has authority to make the request.
2. Verify identity before acting. Obtain the legal name and two supported profile fields (date of birth, email, phone number, or address). Use a declared identity lookup, compare at least two provided fields with the record, obtain the current time, then call `log_verification` with the returned record and timestamp. Do not log verification after a mismatch.
3. Apply all supplied opening eligibility rules. Confirm the required existing account ownership, `OPEN` status, and required balance; any maximum number of business accounts; absence of disqualifying closed accounts; and all product-specific eligibility. Use declared eligibility/account lookup tools when available. Where the policy has no such lookup, ask only for the particular missing confirmation. If a condition is unmet or unanswered, do not open the account.
4. Before opening, confirm the final selected account type/class and review material documented fees, balance conditions, and limits relevant to the account. Do not fabricate irrelevant recipient, card, or cutoff details.
5. If the policy names a specialized opening tool, unlock it and call it once with only the documented parameters after the prerequisites are complete. For `open_bank_account_4821`, use the verified customer ID, `account_type` `business_checking`, and the full selected `account_class`. Treat the tool response as authoritative. Never retry if the result is unknown.
6. Report an opening only after a successful tool result. State the account class, status, and initial balance/date only when returned; otherwise give the reported failure and safe next step.

## Script interface

`scripts/rank_accounts.py` reads one JSON object from standard input and writes one JSON object to standard output.

### Input schema

```json
{
  "requirements": {
    "max_overdraft_fee": 0,
    "min_atm_rebate_monthly": 0
  },
  "promotion_active": true,
  "candidates": [
    {
      "name": "Account name from current evidence",
      "eligibility": "confirmed",
      "overdraft_fee": 0,
      "atm_rebate_monthly": 0,
      "promotion_rank": 1,
      "ordinary_rank": 100,
      "facts": ["Documented fact safe to cite"]
    }
  ]
}
```

The requirement fields are optional numeric values in the evidence's stated currency/unit. `promotion_rank` and `ordinary_rank` are optional positive integers; lower is preferred. Pass only documented strings in `facts`.

### Output schema

On success, output has `status: "recommended"`, a `recommendation`, and excluded candidates with reasons. If no established candidate qualifies, it has `status: "no_confirmed_match"` and `recommendation: null`. Invalid input produces `status: "invalid_input"` and an error.

### Runnable example

```sh
python3 scripts/rank_accounts.py <<'JSON'
{"requirements":{"max_overdraft_fee":0,"min_atm_rebate_monthly":15},"promotion_active":true,"candidates":[{"name":"Example A","eligibility":"confirmed","overdraft_fee":0,"atm_rebate_monthly":20,"promotion_rank":2,"facts":["Zero overdraft fee"]}]}
JSON
```

## Validation before responding

For a recommendation, check that every hard requirement is supported with the documented value, eligibility is `confirmed`, promotion priority was used only among confirmed matches, and all amount/time units are retained. For an opening, check identity verification, authority, all supplied eligibility and product prerequisites, final account selection, and the opening tool result before stating success.
