---
name: checking-referral-eligibility-review
description: Safely review a checking-account customer's ability to make personal or business referrals, including identity verification, referral-history caps, rolling-window checks, and missing eligibility facts. Use for questions about submitting, qualifying for, or tracking checking-account referrals; do not use it to create a referral because this package has no referral-submission action.
---

# Checking Referral Eligibility Review

## Purpose and safety boundary

Use this Skill to determine what can be said about a customer's prospective checking referrals. It distinguishes:

- **referrer eligibility** (verified identity, active checking status, tenure, annual limits, and the cross-product rolling limit),
- **prospective referred-party eligibility** (product, age or business conditions, prior-customer status, address/owner conflicts, and deposit), and
- **qualification after submission** (the deposit and account-standing conditions).

Do **not** represent a prospective referral as approved, complete, or bonus-eligible when required information is missing. Do not create a referral, issue a code, change customer data, or claim a backend check was performed unless an explicitly supplied banking tool actually supports that action.

## Required eligibility-first workflow

The referral policy requires checking whether the user can submit referrals **before** providing referral recommendations or program terms. Follow this order.

1. **Identify and authenticate the referrer.**
   - Obtain a name or user ID and look up the user with the appropriate normal banking lookup tool.
   - Before disclosing account-specific referral history or eligibility, ask the customer to confirm at least two of the four fields returned by the lookup: date of birth, email, phone number, or address.
   - After two fields match, obtain the current timestamp with `get_current_time` and call `log_verification` with the complete record returned by the lookup and that timestamp.
   - Never ask the user to provide a full SSN. A business primary-owner SSN comparison is a back-office eligibility check, not something to collect in chat.

2. **Confirm referrer prerequisites.**
   - Confirm the customer currently has a Rho-Bank checking account in good standing.
   - Obtain the opening date of their **earliest** Rho-Bank checking account when a supported source provides it. Current product type does not determine tenure; the earliest checking opening does.
   - If that date is unavailable, a verified history of a `COMPLETE` referral under a program with a stated tenure threshold can establish that the customer met **that threshold** by the historical completion date, but only if the customer also confirms they still maintain checking in good standing. For example, a completed 45-day program supports present 45-day tenure, not the exact opening date. Use only a threshold that is explicitly documented and no higher than the threshold needed for the prospective product. State this basis clearly; do not fabricate an opening date.
   - Identify the intended product for each prospective referral. Do not infer a product from a prospect's age, school attendance, family relationship, or deposit amount.

3. **Retrieve and assess referral history.**
   - Use `get_referrals_by_user` for the verified user ID.
   - Count only `COMPLETE` referrals toward completed-bonus annual caps and the rolling-bonus limit, unless a program-specific source explicitly says another status counts.
   - Use `scripts/analyze_referrals.py` to calculate counts from a structured transcription of the returned referrals. The script is an aid; the executor must still map actual account-type names and confirm the program cap from the policy reference. Its `indeterminate_requires_exact_timestamp` rolling state is not capacity: obtain the timestamp before promising availability.
   - The rolling cap applies across **all** checking products: no more than two completed bonuses in the preceding rolling nine days. It is based on exact bonus timestamps. If records contain dates only and a result might be close to the nine-day boundary, state that an exact timestamp check is required rather than treating the result as definitive.

4. **Assess each proposed person or business separately.**
   - For an individual, collect the intended account product, full legal name, date of birth where relevant, registered address, and confirmation that the person has had no Rho-Bank checking, savings, or closed account in the prior 12 months.
   - Confirm the individual does not share the referrer's registered address.
   - For a business, collect its intended product and legal formation date. The primary authorized signer/owner must be checked securely against existing Rho-Bank business ownership. Do not request or echo an SSN, and do not say this condition passed unless an authorized back-office result is available.
   - Confirm the proposed deposit is new money, not a transfer from another Rho-Bank account. Explain that it must remain for 30 days after the qualifying period ends.
   - Separate “may be submitted” from “would qualify for a bonus.” A referral can be unready or ultimately non-qualifying even if it is not yet known to violate a cap.

5. **Give a bounded result and next step.**
   - Categorize each prospect as **not available**, **cannot be confirmed**, **potentially available pending checks**, or **appears eligible to submit pending normal account opening/qualification**.
   - Name the particular blocking condition or missing fact. Do not say “eligible” when customer-newness, address condition, business-owner condition, intended product, or an applicable tenure threshold remains unknown. An exact earliest opening date need not remain unresolved if a documented completed-referral record and current good-standing confirmation establish the required threshold under the rule above.
   - If a cap is already exhausted, clearly say no referral bonus slot remains for that product/year. If the rolling cap is reached, explain that additional bonuses will be auto-denied until a prior successful bonus ages out; they cannot be reinstated within that same window.
   - Do not transfer to a human merely because eligibility evidence is incomplete. Ask for the missing information or explain that a secure/back-office check is needed. Transfer only for a supported reason when the customer requests a human or the situation requires one.

## Policy facts to apply

Consult `references/referral_policy.md`. In particular, apply all general restrictions in addition to any product-specific rule. Product-specific conditions do not replace the shared rolling cap, new-customer rule, different-address rule, new-money rule, promotion stacking prohibition, or good-standing requirement.

When there are multiple prospective referrals for a product with only one annual slot left, do not promise both. Explain that only one additional completed bonus can fit the annual cap, subject to all other requirements. Likewise, only available capacity in the shared rolling window can produce an additional bonus at the same time. Distinguish an application/referral from a successful bonus: the rolling rule limits bonuses, while an annual product cap limits bonuses for that product.

## Comparing options after referrer eligibility is supported

Only after the verified referrer has a supported tenure finding and current good-standing confirmation, a customer may ask which prospect maximizes the referrer bonus. Compare only products whose bonus and remaining annual capacity are established. If two qualifying candidates have the same stated referrer bonus, say there is no bonus-maximizing difference rather than inventing one. You may identify a conditional time-sensitive factor (for example, a company apparently close to a documented formation-age limit), but require the exact missing fact and all normal eligibility checks before recommending submission. Never treat an exhausted annual cap as an available option.

Use this decision sequence for each option:

1. Is the target product explicitly identified and are its referral terms in the reference? If not, the option cannot be compared for bonus maximization.
2. Is its annual completed-bonus capacity positive? If not, label the product bonus unavailable for the calendar year, even if the referee otherwise meets its product requirements.
3. Is the shared rolling result definitively below two? If the helper reports a boundary indeterminacy, do not promise immediate bonus capacity.
4. Does the known information meet product gates (such as age, formation age, and deposit amount)? A stated planned deposit is still pending confirmation that it is new money.
5. Are the general new-customer, address, owner-conflict, promotion, and account-standing gates confirmed? If not, phrase the result as pending, not approved.

A recommendation may rank a fully stated, capacity-available option over one that is unavailable or has no documented referral terms; it must never erase unresolved eligibility gates. When a user asks to submit after a recommendation, explain that this Skill cannot submit a referral or issue a code unless a declared banking action explicitly supports it.

## Handling incomplete conversations

Do not repeat facts that the customer has already supplied. A useful concise follow-up should:

1. acknowledge the facts that have been established;
2. state that no referral has been submitted or approved;
3. list only unresolved gate items for each prospect; and
4. ask for authentication fields first if the referrer has not yet been verified.

If authentication has completed and history is available, it is appropriate to correct a customer's recollection of their completed-referral count. Phrase it as the records reviewed, and include the status/year basis of the count. Do not expose unrelated referral IDs or other sensitive details.

## Helper script

`scripts/analyze_referrals.py` receives JSON on stdin and emits JSON on stdout.

Input schema:

```json
{
  "now": "ISO-8601 timestamp with timezone",
  "referrals": [
    {"referred_account_type": "string", "referral_status": "COMPLETE", "date": "ISO-8601, M/D/YYYY, or M/D/YYYY timestamp"}
  ],
  "annual_caps": {"Exact Account Type": 6}
}
```

`annual_caps` is optional and should contain the applicable product caps from the policy. The output contains complete counts by type/year, annual remaining slots for supplied caps, completed bonuses inside the last nine days, date-precision warnings, and lower-boundary referrals excluded from the confirmed rolling count. `rolling_nine_day_state` is `at_cap`, `capacity_available`, or `indeterminate_requires_exact_timestamp`. Account-type matching is exact after surrounding whitespace is removed.

Example invocation by an executor after transcribing the live tool result into the schema:

```bash
python3 scripts/analyze_referrals.py <<'JSON'
{"now":"2025-01-01T12:00:00-05:00","referrals":[],"annual_caps":{}}
JSON
```

Validate the result before relying on it: ensure the `now` timestamp is timezone-aware (the tool's `EST`/`EDT` format is accepted), each referral date was faithfully transcribed, `COMPLETE` is the only status counted, and every cap passed to the script is confirmed by the policy. For a date-only record near the rolling boundary, obtain an exact bonus timestamp through an authorized system rather than claiming a definitive cutoff.
