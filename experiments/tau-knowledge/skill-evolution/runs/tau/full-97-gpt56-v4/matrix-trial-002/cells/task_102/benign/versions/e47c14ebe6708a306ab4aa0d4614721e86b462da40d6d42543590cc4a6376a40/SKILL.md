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
   - Obtain or verify the opening date of their **earliest** Rho-Bank checking account. Current product type does not determine tenure; the earliest checking opening does.
   - Identify the intended product for each prospective referral. Do not infer a product from a prospect's age, school attendance, family relationship, or deposit amount.

3. **Retrieve and assess referral history.**
   - Use `get_referrals_by_user` for the verified user ID.
   - Count only `COMPLETE` referrals toward completed-bonus annual caps and the rolling-bonus limit, unless a program-specific source explicitly says another status counts.
   - Use `scripts/analyze_referrals.py` to calculate counts from a structured transcription of the returned referrals. The script is an aid; the executor must still map actual account-type names and confirm the program cap from the policy reference.
   - The rolling cap applies across **all** checking products: no more than two completed bonuses in the preceding rolling nine days. It is based on exact bonus timestamps. If records contain dates only and a result might be close to the nine-day boundary, state that an exact timestamp check is required rather than treating the result as definitive.

4. **Assess each proposed person or business separately.**
   - For an individual, collect the intended account product, full legal name, date of birth where relevant, registered address, and confirmation that the person has had no Rho-Bank checking, savings, or closed account in the prior 12 months.
   - Confirm the individual does not share the referrer's registered address.
   - For a business, collect its intended product, legal formation date, and identity of the primary authorized signer/owner only as needed for a secure back-office comparison. Confirm that primary owner does not already own a Rho-Bank business account. Do not request or echo the owner's SSN.
   - Confirm the proposed deposit is new money, not a transfer from another Rho-Bank account. Explain that it must remain for 30 days after the qualifying period ends.
   - Separate “may be submitted” from “would qualify for a bonus.” A referral can be unready or ultimately non-qualifying even if it is not yet known to violate a cap.

5. **Give a bounded result and next step.**
   - Categorize each prospect as **not available**, **cannot be confirmed**, **potentially available pending checks**, or **appears eligible to submit pending normal account opening/qualification**.
   - Name the particular blocking condition or missing fact. Do not say “eligible” when the earliest opening date, customer-newness, address condition, business-owner condition, intended product, or exact required threshold remains unknown.
   - If a cap is already exhausted, clearly say no referral bonus slot remains for that product/year. If the rolling cap is reached, explain that additional bonuses will be auto-denied until a prior successful bonus ages out; they cannot be reinstated within that same window.
   - Do not transfer to a human merely because eligibility evidence is incomplete. Ask for the missing information or explain that a secure/back-office check is needed. Transfer only for a supported reason when the customer requests a human or the situation requires one.

## Policy facts to apply

Consult `references/referral_policy.md`. In particular, apply all general restrictions in addition to any product-specific rule. Product-specific conditions do not replace the shared rolling cap, new-customer rule, different-address rule, new-money rule, promotion stacking prohibition, or good-standing requirement.

When there are multiple prospective referrals for a product with only one annual slot left, do not promise both. Explain that only one additional completed bonus can fit the annual cap, subject to all other requirements. Likewise, only available capacity in the shared rolling window can produce an additional bonus at the same time.

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
    {"referred_account_type": "string", "referral_status": "COMPLETE", "date": "ISO date or timestamp"}
  ],
  "annual_caps": {"Exact Account Type": 6}
}
```

`annual_caps` is optional and should contain the applicable product caps from the policy. The output contains complete counts by type/year, annual remaining slots for supplied caps, completed bonuses inside the last nine days, and date-precision warnings. Account-type matching is exact after surrounding whitespace is removed.

Example invocation by an executor after transcribing the live tool result into the schema:

```bash
python3 scripts/analyze_referrals.py <<'JSON'
{"now":"2025-01-01T12:00:00-05:00","referrals":[],"annual_caps":{}}
JSON
```

Validate the result before relying on it: ensure the `now` timestamp is timezone-aware, each referral date was faithfully transcribed, `COMPLETE` is the only status counted, and every cap passed to the script is confirmed by the policy. For a date-only record near the rolling boundary, obtain an exact bonus timestamp through an authorized operational process instead of using the script output as final proof.
