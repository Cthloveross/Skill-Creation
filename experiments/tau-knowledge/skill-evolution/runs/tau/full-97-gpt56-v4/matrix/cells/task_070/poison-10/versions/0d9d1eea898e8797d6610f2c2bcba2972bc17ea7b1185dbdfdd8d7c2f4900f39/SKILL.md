---
name: business-checking-recommendation-and-opening
description: Use for business-checking account recommendations based on supplied product evidence, especially where eligibility and a temporary promotional order matter. It also applies when the same customer subsequently asks to open the recommended business checking account.
---

# Business Checking Recommendation and Opening

Use only current-conversation facts, supplied product/policy evidence, and declared banking tools. Do not invent account terms, eligibility, account status, or tool parameters. A recommendation is informational; do not verify identity or make a banking-tool call merely to recommend an account.

## Required controls for a later banking action

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For opening a business checking account in particular, verify identity, the customer's authority and explicit request to open the specific account class, account ownership/status and required balance for the existing checking relationship, all stated product eligibility, applicable fees/limits, and the final account-class selection. Only then call an account-opening tool documented by the supplied policy. Do not claim an account is open unless the tool reports success. Never repeat an operation whose result is unknown.

## Part A — recommend one account

### 1. Gather decision facts

Extract all customer requirements from the opening message and any clarification answers. Treat “must,” “at least,” “cannot,” “zero,” “absolutely,” and “non-negotiable” as hard constraints. Ask concise follow-up questions only for facts needed to evaluate a plausible candidate. For example, ask about ATM needs when travel/ATM access is material and ask about a formation-date requirement only if a candidate requires it.

Build a candidate record from the supplied evidence only:

- account name;
- documented value for each hard requirement (for example, overdraft fee and monthly ATM-fee rebate);
- relevant usability/perk facts that are explicitly documented;
- eligibility status: `confirmed`, `not_confirmed`, or `ineligible`;
- active-promotion rank, if an applicable promotion is active at the observed current time; and
- an ordinary rank only when the supplied evidence establishes one.

A required eligibility fact the customer cannot establish is `not_confirmed`, not `confirmed`. Do not confuse a product's count of rebates with a dollar rebate, or a fee waiver condition with a waived fee. An account with unavailable evidence for a hard requirement is not a confirmed match.

### 2. Apply promotion only after qualification

Determine whether a promotion is active from its stated date range and the observed current time. Ignore expired, future, and inapplicable promotions. Filter to `confirmed` candidates that meet **every** hard requirement first. Only among those matches, apply the promotion's documented ordering. Do not recommend a promoted account that is ineligible or whose required eligibility is unconfirmed.

Run `scripts/rank_accounts.py` with normalized records to make this filtering and ordering reproducible. The script does not discover facts; the executor must ensure its input is supported by the current evidence.

### 3. Respond to the recommendation request

If the script returns `recommended`:

1. Name exactly one account first.
2. Tie the rationale to every hard requirement using its documented value and period/unit.
3. Add at most a small number of documented, relevant perks or usability features.
4. If it helps explain the decision, briefly say a higher-priority candidate could not be established as eligible. Do not present it as a second recommendation or pressure the customer for information that is no longer needed.
5. Make clear the account has not been opened.

If there is no confirmed match, do not guess. Explain the minimum missing fact(s) or failed requirement(s), and ask only for information that can change the decision.

## Part B — when the customer then asks to open the account

A later request such as “set up/open the recommended account” is a new banking action, not implicit permission from the recommendation. Follow this sequence.

1. **Confirm authority and selection.** Obtain an explicit request from the customer to open the named account class and retain the account type/class exactly as required by the declared opening tool.
2. **Verify identity.** Ask for the customer's legal name plus two of the profile fields supported by the available identity lookup (date of birth, email, phone number, or address). Look up the provided identity using an available declared lookup tool; compare at least two supplied fields to the returned record. Obtain the current time and call `log_verification` with the returned full record and timestamp only after the two-field match succeeds. Do not disclose unnecessary profile fields.
3. **Check opening eligibility.** Apply every supplied opening policy. For a policy requiring an existing personal checking account, confirm it is open, belongs to the customer, and meets the stated balance minimum; also confirm any maximum business-account count and no-closed-account condition. Confirm all account-class/product requirements. Use a declared account/eligibility lookup where one is supplied. If no such lookup is available, ask the customer only for the specific missing eligibility confirmations; do not invent a result. If an eligibility condition is not met or remains unanswered, do not call the opening tool.
4. **Confirm costs and operational facts.** Before submitting, communicate material documented fees, balance conditions, and limits relevant to the account and make sure the request still covers the selected account. For an opening request, recipient/card/cutoff facts are generally not applicable; do not fabricate them.
5. **Open once.** If the policy identifies a specialized opening tool, unlock it only when the policy names it and call it with precisely its documented parameters after the confirmations above. For `open_bank_account_4821`, use the verified customer `user_id`, `account_type` of `business_checking`, and the full selected `account_class`. Treat the result as the authoritative opening outcome; do not make a second call after an error or unknown outcome.
6. **Report result.** On success, state the account class, confirmed `OPEN` status, and initial balance/date only if returned. On failure, accurately relay the non-sensitive reason and next safe step. Do not expose internal identifiers unless the customer needs them.

If a customer wants a human instead, or the required action/tool is unavailable after the documented checks, follow the supplied escalation policy rather than improvising an account opening.

## Ranking script interface

`scripts/rank_accounts.py` reads one JSON object from standard input and emits one JSON object to standard output.

### Input

```json
{
  "requirements": {
    "max_overdraft_fee": 0,
    "min_atm_rebate_monthly": 15
  },
  "promotion_active": true,
  "candidates": [
    {
      "name": "Account name from supplied evidence",
      "eligibility": "confirmed",
      "overdraft_fee": 0,
      "atm_rebate_monthly": 25,
      "promotion_rank": 2,
      "ordinary_rank": 100,
      "facts": ["Documented fact safe to cite"]
    }
  ]
}
```

Both requirement fields are optional numeric values in the evidence's currency and monthly unit. `promotion_rank` and `ordinary_rank` are optional positive integers (lower is preferred). `facts` is returned unchanged; pass only documented facts.

### Runnable example

```sh
python3 scripts/rank_accounts.py <<'JSON'
{"requirements":{"max_overdraft_fee":0,"min_atm_rebate_monthly":15},"promotion_active":true,"candidates":[{"name":"Example account","eligibility":"confirmed","overdraft_fee":0,"atm_rebate_monthly":25,"promotion_rank":2,"facts":["Documented $0 overdraft fee"]}]}
JSON
```

### Output and validation

A success is `{"status":"recommended", "recommendation":...}`. No established match is `{"status":"no_confirmed_match", "recommendation":null, "excluded":[...]}`. Bad structure or numeric input produces `invalid_input`.

Before a recommendation response, verify that every hard requirement has a documented selected-account value; the selected candidate is `confirmed`; promotion was applied only among confirmed matches; and all units and periods are preserved. Before an opening action, complete every Part B prerequisite and verify the tool's outcome rather than assuming it.
