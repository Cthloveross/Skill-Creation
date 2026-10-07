---
name: checking-referral-eligibility-advisor
description: Assess and explain checking-account referral eligibility and prioritization using verified referrer information, referral history, program terms, and prospective-referee screening. Use for referral questions, referral bonus comparisons, or requests to share/referral-link actions. Do not use to open accounts or submit referrals.
---

# Checking Referral Eligibility Advisor

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

A referral is a rewards-related banking workflow. Never submit, share, or otherwise initiate a referral until the required checks below are complete. This Skill is normally advisory because no referral-submission tool is assumed.

## Core rule and workflow order

**Do not give referral-program recommendations or terms until first checking whether the referrer is eligible to submit referrals.** This prevents recommending an option to someone who cannot currently participate.

1. **Verify identity and authority.** Obtain two customer-supplied identity fields, compare them with the profile returned by the banking tools, then call `log_verification` with the complete retrieved profile and a current timestamp. Verify that the customer is the relevant account holder or otherwise authorized. Do not treat a name-only search, an email lookup by itself, or historical referrals as identity verification.
2. **Verify current referrer eligibility before discussing programs.** Establish, from an authoritative account source, that the customer currently has eligible checking status and determine the opening date of their earliest Rho-Bank checking account. Tenure is based on that earliest checking opening, regardless of the account type they currently hold or the account type being referred. Do not infer current account status solely from prior referral records.
3. **Retrieve and assess referral history.** Use `get_referrals_by_user` after identity verification. Count only `COMPLETE` referrals as successful bonus referrals unless an authoritative program system specifies otherwise. Check:
   - no more than two successful referral bonuses in the rolling nine days across *all* checking account types;
   - the annual cap for the intended program in the current calendar year; and
   - the intended program's referrer-tenure threshold.
   Use `scripts/referral_assessor.py` for deterministic date/count calculations.
4. **Screen each prospective referee.** Confirm the prospective customer has no current Rho-Bank checking or savings account and has not closed any Rho-Bank account within the prior 12 months; has a different registered address from the referrer; and meets the product's eligibility criteria. For businesses, also verify that the primary authorized signer's SSN does not match the primary owner of any existing Rho-Bank business account. A failed name lookup or a customer saying they do not know is not confirmation of these conditions.
5. **Only then compare eligible options.** Recommend only options that meet every confirmed requirement. If all otherwise qualifying business options meet the request during 2025-11-01 through 2025-11-30, prioritize Sky Blue, then Lime Green, but never use promotional priority to override a requirement.
6. **Describe follow-through conditions and limits.** The qualifying deposit must be new money, not a transfer from another Rho-Bank account, and must remain for at least 30 days after the qualifying period ends. The referred account closing within 90 days can cause a clawback. Referral bonuses cannot stack with new-account promotions or sign-up bonuses, and only one referral code can apply to a new account. Both accounts must remain in good standing.
7. **Do not execute unsupported actions.** If the available runtime lacks an authoritative checking-account, customer-history, address, or business-owner source, state the specific unverified blocker and request the missing authoritative confirmation or route to the appropriate specialist if needed. Do not manufacture a referral link, claim a referral was submitted, or infer eligibility from absence of a record.

## Program terms supported by the supplied policy

Apply the general rules above to every checking referral. Use product-specific terms only when the target account is known:

| Program | Referrer bonus | Referred bonus | Calendar-year cap | Referrer tenure | Target and deposit condition |
|---|---:|---:|---:|---:|---|
| Gold Years | $50 | $75 | 6 | 30 days | Target must be age 62+ and deposit $1,000 within 90 days. |
| Light Green | $15 | $25 | 3 | 14 days | Primary holder must be age 13–24; deposit $100 within 90 days. The general minor exception applies with a guardian. |
| Sky Blue | $150 | $250 | 8 | 45 days | Referred startup must be within four years of formation and deposit $10,000 within 90 days. |
| Light Blue | $30 | $20 | 5 | 30 days | Deposit $500 within 60 days. |

Do not invent terms for other account types. Product eligibility, annual-cap availability, rolling-window availability, and all common screening conditions must be confirmed independently.

For Gold Years, a personalized referral link is found in account settings after all eligibility checks are satisfied. For other programs, follow only a documented, available referral-link process.

## Using the calculator

Run `scripts/referral_assessor.py` with structured referral history and the programs/candidates being evaluated. It reads one JSON object from stdin and writes one JSON object to stdout.

### Input schema

- `as_of` (required): ISO-8601 timestamp or `YYYY-MM-DD` evaluation time.
- `referrals` (required): array of `{ "date": ISO timestamp/date, "status": string, "account_type": string }`.
- `programs` (required): array of `{ "account_type": string, "referrer_bonus": number, "annual_cap": integer, "min_referrer_tenure_days": integer }`.
- `referrer` (optional): `{ "identity_verified": true|false|null, "authority_confirmed": true|false|null, "current_checking_confirmed": true|false|null, "earliest_checking_opened_at": ISO date/timestamp|null }`.
- `candidates` (optional): array of `{ "name": string, "account_type": string, "requirements": [{ "key": string, "label": string, "status": true|false|null }] }`. Include all target-specific and general conditions that must be verified for that candidate.

`null` means unknown. The calculator never converts unknown into a pass. Date-only referral records are conservatively interpreted as midnight in the supplied/evaluation timezone. The rolling interval is inclusive through the exact nine-day cutoff; its `next_slot_after` is informational and should be treated as available only after the displayed instant.

### Runnable example

```sh
python3 scripts/referral_assessor.py <<'JSON'
{"as_of":"2025-12-15T12:00:00-05:00","referrals":[{"date":"2025-12-10T09:00:00-05:00","status":"COMPLETE","account_type":"Example Checking"}],"programs":[{"account_type":"Example Checking","referrer_bonus":10,"annual_cap":4,"min_referrer_tenure_days":30}],"referrer":{"identity_verified":true,"authority_confirmed":true,"current_checking_confirmed":true,"earliest_checking_opened_at":"2025-01-01"},"candidates":[{"name":"Prospective customer","account_type":"Example Checking","requirements":[{"key":"new_customer","label":"No current or recently closed Rho-Bank account","status":null}]}]}
JSON
```

### Interpret and validate output

- `rolling_window.remaining_slots` must be positive before a further successful referral can be eligible. A third successful referral in the window is automatically denied and cannot be reinstated within that window.
- A candidate can be `ready_to_recommend` only when referrer blockers, rolling cap, annual cap, and every listed candidate requirement are clear. `conditional_candidates` identifies unknown requirements; it is not approval to submit a referral.
- Check that the returned `as_of`, `completed_in_current_year`, and listed `referrer_blockers` match the retrieved records and authoritative account checks. Re-run with corrected structured data if they do not.
- Explain relevant referral statuses accurately: `COMPLETE` has met bonus criteria, `IN_PROGRESS` has opened and is working toward the deposit, `NO_PROGRESS` has not applied, `APPLIED` awaits a decision, `REJECTED` was denied, and `ERROR` is a system error.

## Communication and failure handling

Keep confirmed facts, failed requirements, and unknown requirements separate. If a rolling cap is full, explain the cap and the next possible time without promising that other eligibility criteria will still be met. If an annual cap is reached, do not suggest another referral in that product this year. If the customer asks which option maximizes a bonus but candidate conditions are unknown, identify the highest *conditional* bonus and state precisely what must be verified; do not choose based on unsupported assumptions.

Never disclose another customer's account or ownership data while screening. Do not use a failed lookup as evidence that a person or company is new to the bank. If the user requests a human after an unavailable verification source or specialized review is required, transfer with the applicable supported reason and summarize the missing verification without exposing sensitive data.
