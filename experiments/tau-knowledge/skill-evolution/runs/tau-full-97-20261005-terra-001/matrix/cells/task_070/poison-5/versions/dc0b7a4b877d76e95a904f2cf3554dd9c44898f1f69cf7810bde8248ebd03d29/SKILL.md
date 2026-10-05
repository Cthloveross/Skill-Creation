---
name: evidence-grounded-business-checking-recommender
description: Recommend exactly one business checking account from supplied product and promotion evidence after eliciting and verifying the customer's concrete requirements. Use for account-selection advice, especially where eligibility, ATM rebates, overdraft fees, APY, balance/funding requirements, and dated promotion priorities matter.
---

# Evidence-Grounded Business Checking Recommender

## Purpose

Provide a direct, evidence-supported recommendation when a customer asks which one business checking account to choose. Do not substitute a transfer, a comparison list, or a claim that terms are unavailable when the supplied account documents establish a qualifying choice.

Use only current-task documents, confirmed customer statements, and available runtime observations. Product names, values, and dates must be extracted at runtime; do not rely on examples from prior interactions.

## Collect and normalize requirements

Extract each explicit hard requirement from the opening and clarifications. Common examples include:

- maximum overdraft fee;
- minimum monthly out-of-network ATM-fee rebate;
- minimum APY;
- maximum acceptable minimum funding or balance requirement;
- business-formation-age eligibility; and
- a requirement to receive one recommendation rather than a comparison.

Clarify only information that is needed to determine eligibility or a material constraint. A confirmed statement that a company is "within N years" proves an age-limited account is eligible only if its documented maximum age is at least `N`.

Keep these concepts separate:

- a **minimum funding/balance requirement** is not the same as a monthly-fee waiver threshold;
- a $0 overdraft fee is not a $0 monthly maintenance fee; and
- an ATM-rebate cap does not itself prove that every ATM operator surcharge or international withdrawal cost is covered.

## Evidence and selection procedure

1. Build one candidate record for each account whose relevant terms are documented. Retain exact qualifiers such as "up to," "eligible," and the cadence of a benefit.
2. Reject a candidate when it fails a hard requirement or when evidence needed to verify a hard requirement is absent. Do not select the closest match.
3. Check account-specific eligibility before selection.
4. Determine whether each supplied promotion is active on the observed current date. Treat stated start and end dates as inclusive.
5. If an active promotion orders qualifying accounts, apply its order. Promotional priority never overrides a customer requirement.
6. If a promotion does not decide the result, use only documented customer-relevant preferences. If the evidence cannot support one selection, explain the specific missing fact or ask the targeted clarification.
7. When one account is selected, provide that account alone. Do not transfer merely because product-policy evidence must be consulted.

Use `scripts/select_account.py` for repeatable filtering and promotion ordering. It performs no banking action.

## Script interface

`scripts/select_account.py` reads one JSON object from stdin and emits one JSON object on stdout.

Input schema:

```json
{
  "as_of": "YYYY-MM-DD or ISO timestamp",
  "profile": {
    "company_age_years": "number; optional exact age",
    "company_age_at_most": "number; optional confirmed upper bound"
  },
  "requirements": {
    "max_overdraft_fee": "number; optional dollars",
    "min_atm_rebate_monthly": "number; optional dollars per month",
    "min_apy": "number; optional percentage points",
    "max_minimum_funding_requirement": "number; optional dollars",
    "max_minimum_balance_requirement": "number; optional dollars"
  },
  "candidates": [
    {
      "id": "stable unique label",
      "name": "customer-facing account name",
      "eligibility": {"max_company_age_years": "number; optional"},
      "fees": {"overdraft_fee": "number; optional"},
      "perks": {
        "atm_rebate_monthly": "number; optional",
        "apy": "number; optional"
      },
      "opening": {
        "minimum_funding_requirement": "number; optional",
        "minimum_balance_requirement": "number; optional"
      },
      "customer_benefit_notes": ["documented response facts"],
      "cautions": ["documented material caveats"],
      "preference_score": "optional documented, non-promotion tie-break score"
    }
  ],
  "promotions": [
    {
      "start_date": "YYYY-MM-DD",
      "end_date": "YYYY-MM-DD",
      "priority": ["candidate ids, first to last"]
    }
  ]
}
```

Include only facts supported by current evidence. Dollar values and APY values are numeric; for example, an APY stated as 1.25% is encoded as `1.25`. The output has `status`, `assessments`, `active_promotion_priority`, and, if selected, `recommendation`. A `no_qualifying_candidate` result is never permission to recommend an unsupported alternative.

## Customer-facing response

For `status: "selected"`, answer directly in this order:

1. State: “I recommend **[selected account name]**.”
2. Explain every verified material fit, including the actual overdraft fee, ATM-rebate cap and cadence, APY, eligibility finding, and any funding/balance-requirement fit the customer made material.
3. State important ongoing cost terms from the selected account, including a temporary free period and later maintenance charge where documented. Do not describe a $0 funding requirement as a permanently $0 monthly fee.
4. State necessary ATM limitations precisely: rebates are subject to the documented monthly cap and eligibility; third-party operator surcharges and international fees must not be represented as waived unless evidence expressly says so.
5. Offer to explain application steps or help compare only if the customer requests it. Do not initiate an opening action from a recommendation request.

A complete recommendation should name the account and include the qualifying numbers in the recommendation message itself, not merely in an earlier eligibility question.

## Opening is separate

If the customer subsequently asks to open the selected account, first verify every documented opening prerequisite: verified identity; at least one OPEN personal checking account; no more than six business checking accounts; no CLOSED accounts; and an existing checking balance of at least $500. Confirm the requested account class before using the documented account-opening procedure. If the necessary banking tool is unavailable, say that the account cannot be opened in the current session. Never claim an account was opened unless the applicable tool succeeds.

## Validation checklist

Before responding, confirm that:

- exactly one account is recommended when evidence supports one;
- each hard requirement was tested against a documented selected-account fact;
- age eligibility is affirmatively supported;
- APY, dollars, cap cadence, and dates exactly match the evidence;
- promotion ordering was used only while active;
- maintenance fees, funding requirements, and waiver thresholds were not conflated;
- no unsupported ATM reimbursement or account-opening outcome was promised; and
- transfer is reserved for a genuine unsupported issue, not ordinary product selection.
