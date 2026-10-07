---
name: business-checking-referral-advisor
description: Screen a business-checking referrer and proposed business referral for referral-program eligibility before discussing referral terms, then identify the highest applicable referrer bonus while preserving deposit, tenure, rolling-window, annual-cap, and promotion constraints. Use for referral questions or referral recommendations involving Rho-Bank business checking accounts.
---

# Business Checking Referral Advisor

Use this Skill for informational referral assistance and account recommendations. It does not create referrals, apply codes, move money, or take any other banking action.

## Core safety and policy sequence

1. **Do not give a product recommendation, bonus amount, or referral terms until the proposed referral has been screened for eligibility.** This is mandatory even if the customer asks only which program pays most.
2. Before any account-specific lookup or other banking action, verify the customer's identity according to the available banking workflow (two identity fields when a verification record is required), verify authority and account ownership, and log verification if the provided tools require it.
3. Obtain or verify all of the following before recommending a program:
   - The referrer is a Rho-Bank checking customer and the exact opening date of their *earliest* checking account is known. Tenure is not based on their current product.
   - The referrer has fewer than two successful referral bonuses in the preceding rolling nine days. Count across checking products using exact timestamps. A referral that is exactly nine days old remains in the window; it ages out only after it is more than nine days old.
   - The referred person/business is a new Rho-Bank customer and has not had checking, savings, or a closed Rho-Bank account in the preceding 12 months.
   - The referrer and referred person/business have different registered addresses.
   - For a business referral, the proposed business's primary authorized signer/owner is different from the primary owner of every existing Rho-Bank business account.
   - The intended qualifying deposit is new money, rather than a transfer from another Rho-Bank account.
   - Annual referral-bonus usage is below the selected program's annual cap.
4. If any required fact is unknown, ask only for the missing eligibility confirmation or perform an authorized read-only check. Do **not** fill gaps from the customer's relationship, job history, estimate, or the fact that an LLC was recently formed. Do not reveal product bonus terms while this gate is unresolved.
5. If a fact is false, explain briefly that the proposed referral is not eligible and do not recommend a workaround. If only the rolling limit blocks it, explain that a new referral cannot be reinstated in that same window and must wait until the count falls below two.

The bundled `scripts/referral_assessment.py` can make the date, cap, deposit, and ranking checks deterministic. It is advisory only: the executor must gather the input facts using normal authorized banking tools and must not treat a script result as a banking action.

## Runtime procedure

1. Identify the customer using the supplied name or email. For account-specific information or any action, complete identity verification and any required audit logging first.
2. Retrieve the referrer's referral records using the normal referral read tool. Use only successful/credited bonus timestamps to calculate the rolling-nine-day count. If status or timestamp data are incomplete, treat the limit as unconfirmed rather than assuming it is clear.
3. Obtain the earliest checking-account opening date from an authorized account record or customer confirmation. Do not infer it from credit-card data or the opening date of a current account.
4. Confirm the referred-party new-customer, address, and business-primary-owner conditions. A confirmation that the parties live separately establishes only the address condition; it does not establish new-customer status or distinct primary ownership.
5. Capture the estimated deposit, whether it is new external money, the planned product, and the relevant calendar-year bonus count. Remind the customer that qualifying funds must remain for at least 30 days after the qualifying period and both accounts must remain in good standing. A closure within 90 days may result in a clawback. A referral cannot be stacked with another new-account promotion, and only one code may be used.
6. Send gathered facts to the assessor. For example, provide runtime-collected JSON through standard input:

   `python3 scripts/referral_assessment.py < /path/to/referral_assessment_input.json`

   The script emits a single JSON object on standard output. Its full input and output schema is in the script docstring.
7. Only when `recommendation_permitted` is `true`, compare `eligible_products`:
   - For a customer whose stated goal is the largest referrer bonus, recommend the eligible product with the greatest `referrer_bonus`; do not sacrifice that goal merely because another product has promotional priority.
   - The November 1–30, 2025 promotion ranks Sky Blue first and Lime Green second only when multiple accounts meet **all** stated customer requirements. It never permits recommending one that fails a stated requirement, including a request for the largest available referrer bonus.
   - State the selected product's deposit minimum/window, referrer-tenure threshold, annual cap, and continuing conditions. Do not promise payment; bonuses are paid after qualification and account-good-standing checks.
8. If the customer asks to submit or create a referral after receiving information, recheck identity, authority, eligibility, limits, recipient details, and required confirmation immediately before using the normal banking workflow. This Skill cannot submit the referral.

## Product-policy coverage

The policy catalog at `references/business_referral_programs.json` contains the supported business checking programs and published referral data. The assessor treats missing or unconfirmed runtime facts as unknown. Its recommendation is intentionally suppressed until the submission-eligibility gate, exact product tenure, rolling cap, annual cap, deposit amount, and new-money condition are all confirmed.

Known policy constraints applying to every product include: two successful bonuses maximum in a rolling nine-day period across checking products; different addresses; a new referred customer with no account history in the previous 12 months; distinct business primary ownership; tenure measured from the first checking account; one referral code/no promotion stacking; new-money deposits retained for 30 days after the qualifying period; and possible clawback for a referred account closed within 90 days.

## Validation

A valid assessor invocation returns JSON with `input_errors` as an array, `eligibility_gate`, `product_assessments`, and `recommendation_permitted`. Before relying on it, verify that the runtime facts use booleans or `null`, `as_of` is an ISO-8601 timestamp, monetary values are numeric/decimal strings, and each successful bonus timestamp is ISO-8601. If `input_errors` is nonempty, correct the input and rerun; do not guess the missing facts.
