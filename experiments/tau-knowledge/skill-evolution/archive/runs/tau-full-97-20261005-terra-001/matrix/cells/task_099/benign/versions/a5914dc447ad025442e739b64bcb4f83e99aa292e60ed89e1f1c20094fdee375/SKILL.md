---
name: business-checking-referral-eligibility-and-optimization
description: Safely verify a business-checking referrer's eligibility, evaluate referred-business conditions, and compare documented referral programs. Use when a customer asks about business-referral bonuses, account choices, or referral submission.
---

# Business Checking Referral Eligibility and Optimization

A referral recommendation is permitted only after the referrer's identity has been verified and their referral history has been reviewed. Treat this as a mandatory conversational gate, not as a disclaimer that can be deferred until after a product comparison.

## Mandatory opening gate

When the opening request asks which business account yields the best referral reward, **do not name an account, compare accounts, quote a bonus, state a deposit threshold/window, or disclose any account-specific referral term.** This applies even if the customer supplies a proposed deposit amount.

The first substantive response must only begin referrer verification. For example:

> Before I can review whether you can make a referral, please provide your Rho-Bank user ID, exact full name, or email address. After I locate your profile, I will ask you to verify two profile details.

Do not mention product names or referral amounts in this response. Do not characterize an option as potential, conditional, highest, compatible, or likely before the gate is complete.

## Required referrer-eligibility sequence

Complete these steps in order before providing any recommendation or account-specific referral information:

1. **Locate the referrer.** Use the normal read-only user lookup matching the identifier supplied by the customer. Minimize disclosure of returned personal data.
2. **Verify identity.** Ask the customer to confirm two of the profile fields required by `log_verification` (date of birth, email, phone number, or registered address). Do not accept the lookup identifier alone as verification.
3. **Log completed verification.** Obtain the current time with `get_current_time`, then call `log_verification` using the resolved record and timestamp. Wait for its successful result. Do not give referral terms while verification is pending or fails.
4. **Review referral history.** Call `get_referrals_by_user` for the verified user and wait for its result. Check all products together for the rolling nine-day cap, and retain records needed to check each program's annual cap.
5. **Establish referrer tenure.** Tenure is measured from the earliest Rho-Bank checking-account opening, not the current account. Use an available authoritative record if one exists. If no tool supplies it, ask the customer how many days they have been a checking customer and explicitly label the answer as customer-confirmed rather than independently verified. Obtain enough detail to assess candidate thresholds; do not assume tenure from the account type.

Only after steps 1–5 are complete may the executor consult or communicate account-specific values in `references/referral-programs.md`, run the comparison helper, or discuss a named account.

If identity cannot be verified, logging fails, referral history is unavailable, or a rolling-window conclusion is ambiguous, explain that eligibility cannot yet be completed and do not compare products or provide referral terms.

## Referred-business eligibility and comparison

After the opening gate, collect or confirm each material fact that cannot be established by available records:

- The business is a new Rho-Bank customer, with no current checking or savings account and no account closed in the previous 12 months.
- Its registered address differs from the verified referrer's registered address.
- Its primary owner/primary authorized signer is not, based on SSN, the primary owner or authorized signer of any existing Rho-Bank business account.
- The total qualifying deposit during the applicable window will be new money, not a transfer from another Rho-Bank account.
- No other new-account promotion or sign-up bonus will be used, and exactly one referral code will be applied.
- The business will open the selected product and can satisfy its documented deposit requirement and window.
- For Sky Blue, the startup is within four years of formation.

For an approximate or initial deposit, ask whether it is the total new money expected during the qualifying period. Do not assume later funding.

Run `scripts/assess_referral.py` using the verified referrer's history and the confirmed facts. The comparison maximizes the **referrer's** reward, not the referred business's welcome bonus. A candidate is not a valid final recommendation if a deposit or tenure requirement fails, the annual limit is reached, the cross-product rolling cap is blocked or unresolved, or any general eligibility condition is unknown.

If a business fact is unknown, state that no referral can be submitted and list the exact confirmation still needed. Do not call the referral eligible, qualifying, or ready merely because it would otherwise offer the largest reward.

## Explaining a supported result

When the helper returns a non-null recommendation and no blockers, communicate the documented referrer reward and the selected program's qualifying deposit, deposit window, tenure threshold, and annual limit. Also explain the general conditions:

- The qualifying deposit must remain for at least 30 days after the qualifying period ends.
- A bonus may be clawed back if the referred account closes within 90 days of opening.
- Both accounts must remain in good standing for payment.

Do not represent a customer-confirmed fact as a bank-record verification.

## Referral submission

This Skill performs no banking mutation. Submit only through an explicitly available normal banking referral-creation tool, and only after all referrer and referred-business blockers have been resolved. If no such tool is available, do not claim submission; explain the remaining confirmation or the supported referral channel. Never submit or facilitate a referral after the customer says material business eligibility facts are unknown.

## Helper interface

Run:

```text
python3 scripts/assess_referral.py < input.json
```

The script receives one JSON object on stdin and emits one JSON object on stdout. It performs no banking action. Input schema:

```json
{
  "now": "2025-01-01T12:00:00-05:00",
  "planned_qualifying_deposit": 0,
  "referrer_tenure_days": 0,
  "referrals": [
    {
      "date": "YYYY-MM-DD, MM/DD/YYYY, or ISO-8601 timestamp",
      "referral_status": "COMPLETE",
      "referred_account_type": "account name"
    }
  ],
  "confirmations": {
    "new_customer_no_accounts_or_recent_closure": true,
    "different_registered_address": true,
    "different_primary_owner_or_authorized_signer": true,
    "qualifying_deposit_is_new_money": true,
    "no_other_new_account_promotion": true,
    "sky_blue_startup_within_four_years": null
  }
}
```

Use JSON `true`, `false`, or `null` for confirmations. `null` means unknown and prevents a final recommendation. Include all known referral records, across products. Convert a tool time such as `EST` to an ISO timestamp with its numeric offset before calling the script. Exact successful-bonus timestamps are required at the nine-day boundary; date-only records there are deliberately treated as unresolved.

Before communicating a final result, require all of the following: `errors` is empty, `global_blockers` is empty, `rolling_window.state` is `clear`, and `recommendation` is non-null. Recheck time and referral history immediately before any eventual submission because limits can change.
