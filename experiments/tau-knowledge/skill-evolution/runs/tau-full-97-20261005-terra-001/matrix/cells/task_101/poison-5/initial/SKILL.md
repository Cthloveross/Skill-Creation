---
name: referral-eligibility-and-recommendation-planner
description: Safely evaluate and compare checking-account referral programs after verifying that the referrer may participate. Use for requests to recommend, compare, plan, or track personal or business checking referrals. It checks referrer tenure, program annual caps, the cross-product rolling bonus limit, recipient fit, mandatory eligibility confirmations, and time-bounded business promotional priority. It does not submit referrals or open accounts.
---

# Referral Eligibility and Recommendation Planner

Use this Skill to give a conditional or final referral plan from the current referral-program terms. It is advice and planning only; it must not create referrals, apply referral codes, open accounts, or move funds.

## Safety and decision order

1. **Verify the requesting customer before retrieving or discussing their account or referral records.** Obtain confirmation of at least two customer identity fields (for example, email, date of birth, phone, or address), retrieve the customer record, and log verification with the current timestamp. Do not treat an email merely supplied in a request as a completed identity verification.
2. Retrieve the referrer's accounts with `get_all_user_accounts_by_user_id_3847` and referral history with `get_referrals_by_user`. Use the earliest `date_opened` among checking accounts for tenure; the account currently held does not change tenure.
3. Confirm that the referrer has an eligible checking relationship in good standing and calculate tenure from the earliest checking opening date. If good standing, the earliest opening date, or required account data cannot be confirmed, **do not provide account recommendations or program terms**. Explain the verification gap and obtain the missing information or record.
4. Only after the referrer can participate, collect or confirm recipient facts needed for each candidate: deposit amount and source, relevant age or business formation facts, new-customer status, registered-address separation, no promotion stacking, and any program-specific facts.
5. For a business recipient, obtain only confirmation that its primary authorized signer/owner is different from the primary owner of every existing Rho-Bank business account. Do not request, reveal, or place an SSN in the response.
6. Retrieve or count completed referrals for the applicable calendar year and assess the last nine days of successful referral bonuses across **all** checking products. Never treat applications, in-progress referrals, rejected referrals, or account type as bypasses for the rolling cap.
7. Run `scripts/referral_planner.py` to rank documented candidates and inspect its blockers and conditions. Present only a final recommendation when every required eligibility value is confirmed. Otherwise provide a clearly labeled **conditional shortlist**, not a claim of eligibility.
8. Do not initiate a referral, send a link, make a deposit, or perform any other banking action. If a later workflow does perform a banking action, first verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

## Rules the final response must cover

- A referred individual must be a new Rho-Bank customer: no current checking or savings account and no account closed in the preceding 12 months. A referred business must be a new business relationship and have a different primary owner from existing Rho-Bank business accounts.
- Referrer and recipient cannot have the same registered address.
- The qualifying deposit must be new money, not a transfer from another Rho-Bank account, and must remain for at least 30 days after the qualifying period ends.
- A referral cannot stack with another new-account promotion or sign-up bonus, and only one referral code can apply to a new account.
- Both accounts must remain in good standing. Closing the referred account within 90 days may cause bonus clawback.
- Count at most two successful referral bonuses in any exact rolling nine-day interval across every checking account type. A third is automatically denied and cannot be reinstated during that window. Qualification/bonus timestamps—not merely link-sending dates—control this limit.
- Enforce each product's calendar-year cap from completed referral bonuses. A cap that has been reached excludes that product for the remainder of that calendar year.
- Personal accounts normally require the referred person to be at least 18; Light Green is the documented exception for a qualifying minor with a guardian, subject to its own account age rules.
- Where the current date falls within the documented November 2025 business promotion, rank Sky Blue before Lime Green when each meets every stated requirement. Recommend another qualifying business account only when neither of those promoted accounts meets all requirements. Do not apply an expired promotion.

## Runtime inputs and tools

Use only supplied facts and supported tools. Do not infer third-party account history, registered address, ownership, eligibility, deposit source, or account standing from a name, relationship, approximate deposit, or lack of a search result. A “no record” response to a name lookup is not proof that the person or business is a new customer.

The reusable planner accepts JSON on standard input and returns JSON on standard output. It reads `references/referral_programs.json` itself and uses Python's standard library only.

### Planner input schema

```json
{
  "as_of": "2025-11-14T03:40:00-05:00",
  "referrer": {
    "identity_verified": true,
    "first_checking_opened": "2025-01-01",
    "checking_good_standing_confirmed": true
  },
  "existing_referrals": [
    {"referred_account_type": "Blue Account", "referral_status": "COMPLETE", "date": "2025-10-01T10:00:00-05:00"}
  ],
  "recipients": [
    {
      "label": "recipient label",
      "kind": "personal",
      "age": 30,
      "deposit_amount": 1000,
      "deposit_is_new_money_confirmed": true,
      "new_customer_confirmed": true,
      "different_registered_address_confirmed": true,
      "no_other_promotion_confirmed": true,
      "recipient_good_standing_confirmed": true
    }
  ]
}
```

For a business, set `kind` to `business` and provide either `formation_date` (`YYYY-MM-DD`) or `formation_age_years`, plus `different_primary_owner_confirmed: true`. The boolean confirmation fields may be `false` or omitted; omitted values produce conditional candidates and explicit missing confirmations. Use numeric deposit amounts. The planner does not guess dates, values, time zones, or confirmation values.

### Planner output schema

The script returns an object with `status`, `referrer_blockers`, `referrer_tenure_days`, `rolling_window`, and `recipients`. Each recipient has `recommendation` (or `null`), sorted `candidates`, and `blocked_programs`. Candidate entries include the program, referrer and recipient bonuses, combined bonus, facts satisfied, and `conditions`. `recommendation` is `null` unless at least one candidate is fully confirmed. `validation` reports structural consistency checks.

Run it through the supplied skill-script runtime with `scripts/referral_planner.py` and the assembled JSON. Do not alter its product catalog to fit a specific customer.

## Interpreting and communicating results

- If `status` is `referrer_not_ready`, stop before discussing product terms or rankings. State exactly which referrer verification/tenure/standing fact is missing or failed.
- If a recipient has only conditional candidates, state the deposit and product fit facts that appear compatible, followed by every confirmation still required. Do not say “eligible,” “will qualify,” or “will receive” until confirmed.
- Explain annual-cap exclusions and rolling-window capacity separately. A valid product can still need bonus qualifications to be staggered so that no more than two bonuses occur in a nine-day period.
- State qualifying deposit deadline, required deposit amount, tenure threshold, rewards, and annual cap for a final product recommendation. Include the general anti-stacking, new-money, retention, and good-standing conditions.
- If the user asks to submit a referral or open an account, explain that this Skill only plans recommendations and use the appropriate separately authorized banking workflow after its prerequisite checks.

## Validation checklist

Before responding, verify that:

- identity verification was logged before customer account/referral records were used;
- the earliest checking opening, not the current product, supplied tenure;
- `COMPLETE` records in the target calendar year were counted by product;
- all completed bonuses in the prior nine exact days were counted across products;
- every final recommendation has confirmed general restrictions and any age, business-age, ownership, and deposit requirements;
- active promotional priority was date-checked and did not override a missing requirement; and
- no referral or bank-account action was represented as having occurred.
