---
name: business-checking-recommendation
version: 1.0.0
description: Recommend one business checking account when a customer states requirements and supplied account facts include fees, eligibility, benefits, and any time-bounded promotional ranking.
---

# Business Checking Recommendation

Use this Skill to provide a concise, single-account recommendation. It is for advice only; do not open an account unless the customer explicitly requests it and all documented opening prerequisites have been completed with the normal banking tools.

## Method

1. Extract only explicit customer requirements from the opening message and clarifications. Treat requirements as mandatory rather than as preferences.
2. Obtain the decision date from a supplied observation or the current-time tool. Apply a promotion only while its stated effective dates include that date.
3. Build structured candidate facts from the supplied knowledge. For the supplied account material:
   - **Sky Blue:** company must be within four years of formation; overdraft fee is $0; its free period is six months, followed by a $25 monthly maintenance fee; and its out-of-network ATM fee rebate cap is $15 per month.
   - **Lime Green:** overdraft fee is $0 and its out-of-network ATM-fee rebate cap is $25 per month.
   - During 2025-11-01 through 2025-11-30, rank qualifying accounts Sky Blue first, then Lime Green, then any other qualifying account.
4. Exclude an account whenever an explicit requirement is unsupported, fails, or eligibility is known not to be met. Do not use promotional priority to override a requirement.
5. If more than one account remains, apply the active promotional order. If no promotion applies, state that the available facts do not establish a single best option, or ask one focused clarification if it would resolve the choice.
6. Give the customer one direct recommendation, followed by the two or three facts that show it meets their requirements. Mention material cost/eligibility conditions relevant to the recommended account. Do not burden a customer who asked for one choice with a broad comparison.

For a transparent deterministic selection, run `scripts/recommend.py` with the known facts. The script accepts JSON on stdin and emits JSON on stdout.

### Script input schema

```json
{
  "as_of": "YYYY-MM-DD",
  "requirements": {"no_overdraft_fee": true, "minimum_atm_rebate_monthly": 15},
  "company_within_four_years": true,
  "accounts": [
    {"name": "...", "overdraft_fee": 0, "atm_rebate_monthly": 0, "eligible": true}
  ],
  "promotion": {
    "start": "YYYY-MM-DD", "end": "YYYY-MM-DD",
    "priority": ["..."]
  }
}
```

`accounts` must contain the facts actually supplied for the current task; amounts are numeric USD monthly caps. The result contains `recommendation`, `qualifying_accounts`, and `rejection_reasons`. A missing fact is not assumed to satisfy a requirement.

### Validation and response

Before relying on the result, verify that the recommended account is in `qualifying_accounts`, every mandatory requirement was checked, and the promotion was used only within its date window. Translate the result into a customer-facing answer using the evidence rather than exposing raw JSON.

For the supplied customer facts, confirm the formation-age condition before recommending Sky Blue. Explain its $0 overdraft fee, $15 monthly ATM rebate cap, six-month free period, and subsequent $25 monthly fee. Because the supplied date is in the November 2025 promotion and Sky Blue meets the stated conditions, recommend it ahead of other qualifying options. Do not claim that an ATM operator surcharge is necessarily covered; rebates are limited to eligible out-of-network fees and the monthly cap.

If the customer asks to open an account after the recommendation, follow the documented business-account procedure separately: verify identity, confirm an OPEN personal checking account, no more than six business checking accounts, no CLOSED accounts, and an existing checking balance of at least $500; then obtain the desired account class and use the documented account-opening tool. Do not infer any of these prerequisites from the recommendation conversation.
