---
name: evidence-grounded-business-checking-recommender
description: Evaluate business checking account requests from supplied customer statements, account terms, eligibility rules, and date-bounded promotions. Use when a customer wants one account selected based on fees, ATM rebates, APY, company age, funding, or minimum-balance conditions.
---

# Evidence-Grounded Business Checking Recommender

## Purpose

Provide one evidence-supported business-checking recommendation when possible. When a stated hard requirement cannot be verified from the supplied product evidence, clearly isolate that requirement and distinguish it from facts that are verified. This is advisory only; it neither opens an account nor changes a bank record.

## Read the complete state first

Read the opening request, prior turns, all successful clarifications, supplied documents, and read-only observations before responding. A successful clarification is a confirmed customer answer even if it appears outside the latest conversational turn. Do not repeat a question already answered there.

Extract explicit hard requirements separately from preferences. Common hard requirements include:

- maximum overdraft fee;
- minimum monthly out-of-network ATM-fee rebate;
- minimum APY;
- maximum opening-funding requirement;
- maximum minimum-balance requirement; and
- company-age eligibility.

A request for one account means do not provide a comparison or a list of alternatives unless the customer asks for one.

## Keep product terms distinct

Never infer one of these facts from another:

- **minimum funding requirement** is the amount required to open or fund an account;
- **minimum balance requirement** is a required continuing balance, if one is published;
- **fee-waiver threshold** is a balance that waives a charge; and
- **monthly maintenance fee** is an ongoing account charge.

In particular, a $0 funding requirement does **not** prove a $0 minimum-balance requirement, and a $0 overdraft fee does **not** prove a $0 maintenance fee. Preserve qualifiers such as `up to`, `eligible`, and `per month` for ATM rebates.

## Selection method

1. Build an evidence record for each available account using only documented, account-specific terms.
2. For each customer hard requirement, classify the account term as `meets`, `fails`, or `unresolved` when the needed term is not published.
3. Reject an account that fails a hard requirement. Do not treat an unresolved term as passing and do not recommend a nearest match as qualifying.
4. Verify account-specific eligibility using the confirmed customer facts. A confirmed upper bound establishes an age cap only when the whole confirmed bound is within the documented eligibility maximum.
5. If promotional priority matters, use the observed current date and treat start and end dates as inclusive. Apply an active promotion only among accounts that meet **all** hard requirements; it never overrides a failed or unresolved requirement.
6. If one or more candidates fully qualify, select exactly one using active promotional order, then an explicitly documented customer-relevant tie-breaker.
7. If no candidate can be safely selected because a material term is unresolved, do not transfer merely for ordinary product selection. State the exact term that needs verification and the account facts that are published. If an appropriate information source is available in the runtime, seek that specific term; otherwise explain that it must be verified before a qualifying one-account recommendation can be made.

Use `scripts/select_account.py` for deterministic filtering after extracting evidence. The script is advisory and performs no banking action.

## Script interface

Run `scripts/select_account.py` with one JSON object on stdin. It writes one JSON object to stdout.

```json
{
  "as_of": "YYYY-MM-DD or ISO timestamp",
  "profile": {
    "company_age_years": "number, optional exact age",
    "company_age_at_most": "number, optional confirmed upper bound"
  },
  "requirements": {
    "max_overdraft_fee": "number, optional dollars",
    "min_atm_rebate_monthly": "number, optional dollars/month",
    "min_apy": "number, optional percentage points",
    "max_minimum_funding_requirement": "number, optional dollars",
    "max_minimum_balance_requirement": "number, optional dollars"
  },
  "candidates": [
    {
      "id": "stable identifier",
      "name": "customer-facing account name",
      "eligibility": {"max_company_age_years": "number, optional"},
      "fees": {"overdraft_fee": "number, optional"},
      "perks": {"atm_rebate_monthly": "number, optional", "apy": "number, optional"},
      "opening": {
        "minimum_funding_requirement": "number, optional",
        "minimum_balance_requirement": "number, optional"
      },
      "customer_benefit_notes": ["documented facts"],
      "cautions": ["documented caveats"],
      "preference_score": "optional documented tie-break score"
    }
  ],
  "promotions": [
    {"start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD", "priority": ["candidate ids"]}
  ]
}
```

Use numeric dollars and percentage points (`1.25%` is `1.25`). Include only facts supported by the current task evidence. The result contains per-candidate `failed_requirements` and `unresolved_requirements`, active priority, and either a selected recommendation or a safe non-selection status.

Example shape:

```json
{
  "as_of": "<observed date>",
  "profile": {"company_age_at_most": "<confirmed bound>"},
  "requirements": {"min_apy": "<customer minimum>"},
  "candidates": ["<evidence-derived records>"],
  "promotions": ["<evidence-derived promotion records>"]
}
```

## Customer-facing response

### When `status` is `selected`

Put all qualifying information in the same recommendation message:

1. Say unambiguously, `I recommend [account name].`
2. Confirm each hard-requirement fit with exact documented numbers and cadence.
3. State age eligibility when applicable.
4. Disclose material ongoing costs, including any limited free period followed by a maintenance fee.
5. Describe ATM rebates faithfully, including `up to`, monthly cap, eligibility, and any documented limitations.
6. Offer application information only; do not start opening an account unless asked.

### When `status` is `insufficient_evidence`

Give a useful, precise safe deferral rather than a blanket catalog denial or human transfer. Name the account only as a **potential** fit, never as a qualifying recommendation. State:

- the exact unresolved hard term (for example, the published minimum-balance requirement);
- the verified terms relevant to the request, with figures and qualifiers;
- the verified eligibility result, if applicable; and
- any documented maintenance-fee caveat.

For example, say that the published material does not establish the minimum-balance requirement and therefore does not yet support confirming a qualifying one-account recommendation. Do not say that all account terms are unavailable when several terms are documented. Do not characterize a $0 funding requirement as satisfying an unresolved minimum-balance requirement.

### When `status` is `no_qualifying_candidate`

State which hard requirement each plausible candidate fails, without presenting a failing account as the answer. If a customer relaxes a requirement, re-evaluate using the newly stated constraint.

## Opening is separate

If the customer asks to open an account after selection, verify every documented prerequisite before any opening action: verified identity, at least one OPEN personal checking account, no more than six business checking accounts, no CLOSED accounts, and the required existing-checking balance. Confirm the desired account class before using the documented opening procedure. If a required banking tool is unavailable, say the account cannot be opened in the session; never claim success without a successful tool result.

## Validation checklist

Before responding, ensure that:

- successful clarifications were used and not re-asked;
- each hard requirement was compared to the same kind of documented term;
- unknown terms were called unresolved rather than assumed to pass;
- a selected account is the sole recommendation and all its material qualifying figures appear in that message;
- a non-selection identifies the specific blocking requirement and communicates available relevant facts;
- APY, amounts, cadence, dates, eligibility, and fee caveats match the evidence;
- promotion priority was active and applied only among fully qualifying accounts; and
- no unsupported reimbursement, product term, account-opening outcome, blanket terms-unavailable claim, or unnecessary transfer was made.
