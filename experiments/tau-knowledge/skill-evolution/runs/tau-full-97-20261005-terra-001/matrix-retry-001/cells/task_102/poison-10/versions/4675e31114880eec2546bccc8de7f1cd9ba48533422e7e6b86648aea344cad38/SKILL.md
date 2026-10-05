---
name: checking-referral-screening-and-recommendation
description: Screen a checking-account referrer's eligibility before discussing referral recommendations, match prospective personal or business referrals to supported account programs, calculate annual and rolling referral constraints, and identify information that must be verified before a referral or account-opening action.
---

# Checking Referral Screening and Recommendation

Use this Skill for requests to recommend checking accounts in connection with a referral, assess whether a referral can proceed, or explain applicable referral qualification conditions. It supports read-only screening and recommendations only: it does not submit referrals, open accounts, or promise a bonus.

## Banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

A name lookup is not identity verification. If a request advances to an available banking action, verify two of date of birth, email, phone number, and address, then call `log_verification` before acting. Use only tools actually available in the runtime.

## Inputs and fact ledger

Gather, at minimum:

- Referrer identity or user ID, current time, and proposed account type(s).
- Referrer's account history, especially the earliest checking opening date. Tenure is measured from the oldest checking account, not the product currently held.
- Referrer's referral history, including status, target account type, and completion/bonus timestamps where available.
- For an individual, age and product-specific facts; for a business, formation age and primary authorized signer/owner.
- Before submission, confirmation that the referred party is a new customer with no existing checking or savings account and no account closed within the last 12 months, has a different registered address, and, for businesses, has a different primary owner than every existing Rho-Bank business account.

Maintain a fact ledger. A fact supplied by the customer or in a clarification is established unless internally inconsistent. Do not re-request it, characterize it as unknown, or say that it needs confirmation. Keep documentary requirements separate from established facts.

For example, if a candidate is stated to be 19 and currently enrolled, state that the candidate meets the applicable age requirements based on the supplied age. For Dark Green, acceptable current-semester enrollment documentation may still need to be verified; say that enrollment documentation is needed, never that the candidate's age or being at least 18 needs reconfirmation.

## Read-only screening order

**Complete this screen before giving referral recommendations or referral-program details.**

1. Resolve an unambiguous referrer using an available read-only lookup, then retrieve referral history. Retrieve account history with `get_all_user_accounts_by_user_id_3847` when available.
2. Get the current time before assessing the rolling window.
3. Determine checking tenure from the earliest checking account opening date.
4. Count `COMPLETE` referrals by program in the current calendar year and compare each to its annual cap.
5. Count completed referral bonuses in the exact trailing nine-day interval across all checking programs. Do not use calendar weeks. If a date-only record is near the cutoff, obtain an exact timestamp rather than declaring it outside the window.
6. For each target, confirm referrer tenure, program annual capacity, and shared rolling capacity. A blocked program must not be presented as a currently bonus-eligible referral.
7. Only after the referrer screen passes for a target, assess product match and identify recipient-side conditions still requiring validation.

The shared rolling cap is two successful referral bonuses in any rolling nine-day window. Qualification dates, rather than application dates, determine its impact. Multiple referrals may be in progress, but do not imply that they will all qualify simultaneously.

## Program matching rules

Use `references/referral_programs.json` as the supported catalog. Do not invent benefits, caps, deposits, deadlines, or product fit.

- **Dark Green Account:** product age range is 17–26, while a referral candidate is subject to the general 18+ rule. The referrer needs 45 days of checking tenure; a qualifying referral requires a $1,000 deposit within 60 days; annual cap is six. Current enrollment must be verified each semester.
- **Gold Years Account:** recipient must be 62 or older. Referrer tenure is 30 days; qualifying deposit is $1,000 within 90 days; annual cap is six.
- **Sky Blue Account:** company must be within four years of formation. Referrer tenure is 45 days; qualifying deposit is $10,000 within 90 days; annual cap is eight. In the documented November 1–30, 2025 promotion window, prioritize Sky Blue only if multiple business products satisfy every stated requirement.
- Do not claim that other catalog programs are suitable if authoritative product-fit information is incomplete.

For every potentially qualifying referral, explain as relevant that qualifying funds must be new money rather than a transfer from another Rho-Bank account and must remain for at least 30 days after the qualifying period. Only one referral code may apply; referral bonuses cannot stack with other new-account promotions. A bonus may be clawed back if the referred account closes within 90 days, and both accounts must remain in good standing.

## Running the helper

Run `scripts/review_referrals.py` with a JSON object on stdin using `run_skill_script`. It reads only the supplied JSON and the packaged catalog and makes no bank changes.

Input schema:

```json
{
  "now": "ISO-8601 timestamp or YYYY-MM-DD HH:MM:SS TZ",
  "referrer": {"earliest_checking_opened": "ISO date or timestamp"},
  "referrals": [
    {
      "referred_account_type": "Gold Years Account",
      "referral_status": "COMPLETE",
      "completed_at": "ISO timestamp or MM/DD/YYYY"
    }
  ],
  "candidates": [
    {
      "label": "prospective-person",
      "account_type": "Gold Years Account",
      "profile": {"kind": "person", "age": 65}
    }
  ]
}
```

The script emits JSON containing `errors`, `screening_complete`, a shared `rolling_window`, annual counts, and one result per candidate. `product_fit.established_conditions` contains facts already satisfied; never reframe these as pending. `referral_recommendation_permitted` is true only when the program is known, tenure is established and sufficient, the annual cap has capacity, and the rolling limit is available.

Before relying on helper output, validate that `errors` is empty and `screening_complete` is true. A target with `unknown`, `ineligible`, or `blocked` status is a stop for a bonus-eligible referral recommendation. A `conditional` product fit must identify its exact remaining proof.

## Customer response requirements

Give a concise, decision-oriented response that:

1. States whether the referrer screen was completed and whether shared nine-day capacity affects timing.
2. Uses recorded history, rather than a customer's estimate, for annual counts and the most recent completed referral date.
3. For each candidate, first identifies established facts and conditions already met, then lists only unresolved requirements.
4. Names a referral target only if it is both a product match and currently referral-permitted. If an annual cap is exhausted, say it is not currently available as a bonus-eligible referral.
5. Separately identifies required checks: new-customer/12-month history, different address, business-owner comparison, exact rolling timestamps where needed, qualifying deposit, and required enrollment documentation.
6. Does not expose another person's record or represent an application, account opening, referral creation, or bonus as completed without a corresponding available tool action and observed result.

Every read-only recommendation or screening response must plainly include this exact operational disclosure: **“I cannot create or submit a referral, and no account has been opened.”** This is required even when the user did not expressly ask for submission.

If an owner-record comparison or another mandatory eligibility check cannot be performed with available tools, state that eligibility cannot yet be confirmed rather than guessing.

Referral-status meanings, if requested: `COMPLETE` means criteria were met; `IN_PROGRESS` means the account is open but the deposit requirement is unmet; `NO_PROGRESS` means no application; `APPLIED` means awaiting a decision; `REJECTED` means denied; and `ERROR` means a system error.
