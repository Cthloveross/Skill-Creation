---
name: business-checking-referral-advisor
description: Safely handles requests to refer a business to a Rho-Bank business checking account, including eligibility-first checks, referral-program comparison, and account-opening prerequisites. Use when a customer asks which business checking referral offers the best bonus or asks to create a referral or open a referred business account.
---

# Business Checking Referral Advisor

## Purpose and safety boundary

Determine whether a referral can be considered before discussing referral terms or recommending an account. Do not create a referral, open an account, or imply approval from incomplete information. All bank reads and writes must use the normal banking tools supplied in the current runtime; this package only analyzes facts supplied to it.

Read `references/referral_policy.md` before assisting. The product catalogue and general restrictions in that reference are policy facts, not customer facts.

## Required workflow

1. **Identify and verify the requesting referrer first.**
   - Obtain the referrer's full name or email, look up the user with the appropriate banking tool, and have the user confirm two identity fields.
   - If two fields are confirmed, obtain the current timestamp and log verification using the normal `log_verification` tool.
   - Read the referrer's referral history. Count `COMPLETE` referrals whose successful-bonus timestamps fall in the preceding rolling nine days, and count completed bonuses in the current calendar year.
   - Determine tenure from the earliest Rho-Bank checking-account opening date, not the product currently held. Use an available account-history read; if the runtime cannot supply that fact, request the exact opening date or state that tenure cannot yet be verified.
   - Do not provide referral-program terms or a product recommendation until this referrer check is complete. A user with two successful bonuses in the last nine days is ineligible for another referral during that window.

2. **Collect and verify the prospective referred business facts.**
   Require the prospective customer's full name or email before attempting customer/account checks. Confirm or retrieve all of the following:
   - The person/business is a new Rho-Bank customer with no existing checking, savings, or account closed in the last 12 months.
   - The registered address differs from the referrer's address.
   - The prospective owner is age-eligible. (The business products here use the normal adult requirement.)
   - The LLC's primary authorized signer is known and has a different SSN from the primary owner of every existing Rho-Bank business account.
   - The deposit is new money, not a transfer from another Rho-Bank account, and the customer can retain it at least 30 days after the applicable qualification period.
   - No conflicting new-account promotion or sign-up bonus will be used, and only one referral code will be applied.

   If the name/email or primary-signer confirmation is unavailable, explain that eligibility cannot be verified and stop. Do not guess based on a relationship description, separate residence, or incorporation status.

3. **Check the referred customer's account-opening prerequisites separately.**
   For a business checking account, the actual applicant must be verified and must have: an OPEN personal checking account with at least $500, no CLOSED accounts, fewer than six business checking accounts, and a chosen `account_class`. If any condition is unmet or unknown, do not invoke the account-opening tool. Account opening is not a substitute for referral eligibility verification.

4. **Evaluate products only after the above checks pass.**
   - Check program-specific referrer tenure, deposit amount, deposit deadline, annual cap, and any account-specific restriction.
   - Exclude a program if the planned funding is below its qualifying threshold, its tenure is insufficient, its annual cap is exhausted, or a required fact is unknown.
   - Apply the cross-product rolling nine-day cap in addition to each product's annual cap.
   - For a request for the largest referrer bonus, choose the highest bonus among fully qualifying programs. Explain material ongoing account conditions that are documented for the selected product.
   - The November 2025 Sky Blue/Lime Green priority applies only when those accounts satisfy *all* stated requirements. A request for the largest referrer bonus means a lower-paying promotional product does not satisfy that stated requirement. For a tie, apply the active promotional priority.
   - Use `scripts/evaluate_referral.py` for consistent filtering and ranking when the requisite facts have been gathered.

5. **Execute only supported, authorized actions.**
   - If all referral checks pass and the customer asks to proceed, use only the normal referral workflow exposed by the runtime. Do not infer an unexposed referral-creation tool.
   - Open a business account only for a verified, eligible applicant after they select an account class, using the documented normal opening procedure/tool available in the runtime.
   - Do not retry a referral reported as `REJECTED` for the rolling cap; it cannot be reinstated within that same window. For `ERROR`, report the system issue and follow normal support/escalation procedures rather than treating it as approved.

## Handling incomplete information

When required prospective-customer information is missing, give a concise blocking response such as: the referral cannot be assessed or submitted yet because the prospective customer's identity and primary authorized signer must be checked against new-customer and business-owner restrictions. Request their full name or email and confirmation that they will be the LLC's primary signer. Do not name a recommended product, quote a bonus, or promise eligibility at that stage.

If the referrer is not eligible, state the specific verified blocker (for example, tenure, annual cap, or rolling-window timing) and, when calculable, state what information or passage of time is needed. Do not recommend a workaround that bypasses a restriction.

## Analysis helper

`scripts/evaluate_referral.py` reads one JSON object from stdin and emits one JSON object to stdout. It performs no bank actions.

Input schema:
- `now`: ISO-8601 timestamp with timezone.
- `request`: object with `maximize_referrer_bonus` (boolean) and optional `active_promotion_priority` (ordered product names).
- `referrer`: `tenure_days`, `complete_bonus_timestamps` (ISO timestamp array), and `annual_complete_count`. Use JSON `null` for unknown facts.
- `referred`: boolean or null gates named `identity_confirmed`, `new_customer`, `different_address`, `age_eligible`, `primary_signer_confirmed`, `distinct_business_primary_owner`, `new_money_deposit`, `deposit_retention_possible`, `no_conflicting_promotion`, and `account_opening_eligible`.
- `products`: array of objects containing `name`, `referrer_bonus`, `annual_cap`, `required_deposit`, `deposit_window_days`, `required_tenure_days`, and optional `company_max_age_years`.
- `planned_deposit` and optional `company_age_years`.

Run it with a gathered-facts JSON file, for example: `python3 scripts/evaluate_referral.py < gathered_facts.json`. Validate that `recommendation` is non-null before presenting a recommendation. A nonempty `blockers` or `missing_evidence` result means the operator must resolve those items first.
