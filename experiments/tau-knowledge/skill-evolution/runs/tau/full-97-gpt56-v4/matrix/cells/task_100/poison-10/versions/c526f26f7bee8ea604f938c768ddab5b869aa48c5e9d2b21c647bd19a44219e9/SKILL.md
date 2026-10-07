---
name: business-checking-referral-eligibility
version: 1.0.0
description: Safely determine whether a checking customer may receive a business-referral recommendation, verify universal and product-specific referral conditions, and select the highest qualifying referrer bonus without creating a referral.
---

# Business Checking Referral Eligibility and Bonus Comparison

Use this Skill when a customer asks which business checking referral program offers the best bonus, whether a referral can qualify, or why a business referral may be unavailable. It is for advice and eligibility review only; it does not submit referrals, change accounts, or disclose another person's information.

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For an account-specific review, verify the customer under the available identity procedure before accessing, relying on, or disclosing profile-specific referral history. Confirm two of the four identity fields (date of birth, email, phone number, address), retrieve the profile only through the approved banking tools, and record successful verification with `log_verification` and a current timestamp. Do not treat a name alone, an email address alone, or an unverified assertion as two factors.

## Critical ordering rule

Before giving **any referral recommendation or referral-program terms**, establish that the referrer can participate. If eligibility is incomplete, do not rank products, name a "best" bonus, quote program bonus amounts, or imply a referral will qualify. Explain that the comparison is deferred and state only the missing confirmations and safe next steps.

A prior conversation may contain read-only observations. Use them only if they are attributable to the authenticated customer and still adequate for the check; do not repeat a lookup merely to obtain a more favorable answer. Never put a customer identifier, history, or conclusion from a particular conversation into this package.

## Eligibility-review workflow

1. **Classify the request.** Confirm that the customer wants a referral recommendation rather than a referral submission. There is no referral-creation action in this workflow.
2. **Authenticate before account-specific inquiry.** Follow the mandatory banking control. Then use the normal banking tools to locate the authenticated user and retrieve `get_referrals_by_user`. Use `get_current_time` when a verification log is required.
3. **Check referral-history limits.** Determine the timestamps of successful/bonus-earning referrals, not merely applications or referrals in progress. There may be no more than two bonuses in the 9 days immediately preceding the proposed referral time, across all checking products. Also count qualifying bonuses in the relevant calendar year for a product's stated annual cap. If timestamps, statuses, or history cannot be reliably determined, mark the limit check as unresolved rather than assuming it passes.
4. **Establish universal conditions.** Obtain or verify all of the following before a recommendation:
   - The proposed referred business/customer is new to Rho-Bank and has had no existing checking, savings, or closed account in the preceding 12 months.
   - The parties have different registered addresses.
   - For a business referral, the business has a primary owner/primary authorized signer whose SSN is distinct from the primary authorized signer of every existing Rho-Bank business account.
   - The referrer has sufficient tenure measured from the **earliest Rho-Bank checking account opening**, regardless of their current account type.
   - The proposed qualifying deposit is confirmed new money, not a transfer from another Rho-Bank account.
   - Both accounts can remain in good standing. The qualifying deposit must remain for at least 30 days after the qualification period, and an account closed within 90 days can cause a clawback.
   - The referral will not be combined with another new-account promotion and only one referral code will be used.
5. **Handle third-party information safely.** Do not request, reveal, or compare SSNs in chat. The prospective business's authorized representative must confirm signer/owner eligibility through the appropriate secure onboarding or relationship-manager process. If the customer cannot confirm that condition, eligibility is unresolved and the comparison must remain deferred.
6. **Evaluate product requirements only after the preceding checks pass.** Obtain an exact or reliably confirmed deposit amount, not an estimate, and compare it with each product's minimum deposit and tenure requirement. Check any product-specific admission requirements separately (for example, startup or enterprise criteria).
7. **Calculate consistently.** Normalize the collected facts and run `scripts/rank_referral_options.py`. Its `recommended_program` is usable only when its `decision` is `recommendation_ready`. Treat `defer` or `no_qualifying_program` as authoritative reasons not to offer a best-program recommendation.
8. **Respond narrowly and accurately.**
   - If deferred: say eligibility cannot yet be confirmed; list the exact unresolved checks without exposing third-party data; invite the customer or prospective business's authorized representative to complete them securely.
   - If no program qualifies: explain the relevant high-level blocker(s), such as insufficient confirmed new-money deposit or tenure, and do not suggest bypassing requirements.
   - If ready: identify the highest referrer bonus among the qualifying programs, state its qualifying deposit window and tenure requirement, annual/rolling limits, and general retention/good-standing conditions. Describe it as conditional on the facts verified, never as guaranteed.

Do not create a referral, apply a code, access another person's profile, or claim an unverified account-opening date, deposit source, signer status, or referral status.

## Program reference

Use `references/business_referral_programs.json` as the product catalog. It records only published program requirements from the supplied source material. General referral restrictions apply to every entry in addition to the catalog fields. When published materials omit a needed product condition, keep that condition unresolved rather than inventing it.

## Calculator interface

Run `scripts/rank_referral_options.py` through the packaged script runner. It reads one JSON object from standard input and emits one JSON object to standard output.

Input schema:

- `as_of` (string, required): ISO-8601 instant at which the rolling window is evaluated.
- `programs` (array, required): catalog objects with `name`, `referrer_bonus`, `required_deposit`, `deposit_window_days`, `tenure_days`, and optional `annual_limit`.
- `confirmed_new_money_deposit` (number or `null`): exact confirmed qualifying amount; use `null` for an estimate or unknown amount.
- `referrer_tenure_days` (integer or `null`): days since the earliest checking opening.
- `recent_successful_bonus_timestamps` (array of ISO-8601 strings or `null`): successful-bonus timestamps across all products. Use `null` when history was not verified.
- `annual_bonus_counts` (object or `null`): qualifying-bonus count for each program name in the current calendar year.
- `common_checks` (object): boolean or `null` values for the universal checks. Required keys are `identity_verified`, `new_customer`, `different_registered_address`, `distinct_business_primary_owner`, `new_money_confirmed`, `both_accounts_good_standing`, `promotion_stacking_clear`, and `recent_bonus_history_verified`.
- `program_checks` (object, optional): per-program boolean or `null` checks for product-specific admission rules.

The output separates `blockers` from `unknowns`, lists each program's viability, counts the rolling-window bonuses, and returns a recommendation only when every required common check is true and a fully eligible product exists. Validate that the script output has a `decision`, `common_blockers`, and `programs` array before using it in a response.

The executor should build input from current, authenticated runtime facts and the catalog, rather than embedding customer values in scripts or documentation.
