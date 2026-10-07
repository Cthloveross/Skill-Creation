---
name: referral-bonus-status-inquiry
description: Safely investigate and explain why a credit-card referral bonus has not posted. Use for customer questions about referral status, qualification requirements, referral limits, and expected payout timing; do not use it to issue, alter, or reinstate a reward.
---

# Referral Bonus Status Inquiry

Use this workflow to provide a factual status explanation for a referral bonus that is pending or missing. It supports read-only investigation and customer communication only. There is no authority in this Skill to manually grant a bonus, change a referral status, override a limit, or access a referred person's private account activity.

## Mandatory banking controls

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes;

For a referral inquiry:

1. Identify the customer using a customer-provided account identifier.
2. Before disclosing nonpublic referral-record details or taking any account action, confirm at least two of the four identity fields (date of birth, email, phone number, and address) against the retrieved customer profile.
3. Obtain the current timestamp and create the required verification audit record using the normal `log_verification` tool after successful two-field verification.
4. Confirm that the referral record's `referrer_id` belongs to the verified customer. Do not discuss records belonging to another customer.
5. Do not ask for, reveal, or attempt to retrieve the referred person's transactions or other private account details. A referrer's own card transactions do not establish whether the referred person met a spending condition.

If the runtime already supplies read-only observations from a completed, authorized investigation, use those observations as evidence but do not perform an additional account action merely to reproduce them. If authorization has not been established and more record detail is needed, request the missing verification fields rather than guessing.

## Investigation workflow

1. **Clarify the referral.** Ask for the referred card type and approximate referral date if the customer has more than one referral. If the customer says “most recent,” select the record with the newest reliably parsed date; do not assume that list display order is chronological.
2. **Read the referral record.** Obtain the verified customer's referrals with the normal referral lookup. Record the selected referral's card type, date, and status exactly as returned. Use `scripts/summarize_referrals.py` if normalized records must be sorted consistently.
3. **Apply the product-specific terms.** For a Silver Rewards Card referral, the referred person must be approved and spend at least $750 within 60 days of account opening. The referral bonus typically posts one to two billing cycles *after* that requirement is met. Approval, opening, card activation, or initial transactions alone do not establish that the spend threshold has been met.
4. **Consider program availability and limits without overclaiming.** Referral offers and requirements are card-specific, and not every card participates. Across credit-card types, no more than two successful referral bonuses are allowed in a rolling seven-day window; later referrals in that window are automatically denied. Separately, Silver Rewards Card terms state a maximum of seven referral bonuses per calendar year. Determine a rolling-window decision only from actual successful-bonus timestamps, not from referral creation dates or `COMPLETE` dates when timestamps are absent. If required dates/timestamps or card-specific terms are unavailable, say that eligibility cannot be confirmed from the available record.
5. **Explain the result accurately.**
   - `IN_PROGRESS`/pending: explain that the referral is still being tracked and the spend requirement must be met before payout timing begins.
   - `COMPLETE`: explain that the status alone does not prove the payout date; compare known qualification and payout information, and do not promise a posting date.
   - `REJECTED`: report only a stated reason. Do not attribute rejection to a limit without evidence of the relevant successful-bonus timestamps.
   - `ERROR` or missing/inconsistent record: do not speculate. Escalate to a human agent as a technical system error with the referral identifier, observed status, and investigation performed.
6. **Close with an appropriate next step.** For a pending qualifying referral, advise the customer that the referred person needs to meet the applicable threshold within the permitted period and that the expected posting window begins after that condition is met. For an apparently overdue, fully qualified referral whose applicable terms and limit status have been verified, explain that the case needs specialist review; transfer using the available human-transfer path when necessary. Never state that a bonus will definitely post.

## Communication rules

- Lead with the specific status and the applicable requirement, then state the timing in plain language.
- Distinguish confirmed facts (record status, card type, date) from unknowns (referred person's qualifying spend, account-opening date, actual bonus-post timestamp).
- Do not expose full account identifiers, personal data, or another person's information in the response.
- Do not treat a referral date as the referred account's opening date.
- Do not calculate an exact billing-cycle payout date unless the billing-cycle dates are actually available.
- When the record is too new or still pending, explain why a bonus is not yet expected rather than calling it missing.

## Optional deterministic helper

`scripts/summarize_referrals.py` selects the latest referral from normalized records and identifies successful bonus events that have enough timestamp precision for a rolling-seven-day review. It does not make eligibility, spend, or payout promises.

Run it by sending JSON on standard input and receiving JSON on standard output:

```json
{
  "as_of": "2025-01-15T12:00:00-05:00",
  "referrals": [
    {"referral_id": "optional", "account_type": "Card type", "status": "IN_PROGRESS", "date": "2025-01-14"}
  ],
  "successful_bonus_timestamps": ["2025-01-13T10:00:00-05:00"]
}
```

The output has `latest_referral`, `successful_bonus_count_in_previous_7_days`, `rolling_limit_assessable`, and `warnings`. Validate that `latest_referral` matches the intended customer-selected referral, and treat any warning or `rolling_limit_assessable: false` as a reason not to make a limit determination.
