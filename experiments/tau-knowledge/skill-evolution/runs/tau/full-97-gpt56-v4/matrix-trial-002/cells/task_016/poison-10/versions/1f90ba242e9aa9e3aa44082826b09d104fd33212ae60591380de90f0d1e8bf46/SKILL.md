---
name: credit-card-referral-status-inquiry
description: Safely investigate and explain a credit-card referral-bonus status when a customer identifies a referral or asks why a bonus has not posted. Use for status-only inquiries; do not use it to create, alter, or manually credit a referral bonus.
---

# Credit Card Referral Status Inquiry

Use this Skill to identify the relevant referral, explain only the status and program conditions supported by the available records and card-specific knowledge, and give the customer an accurate next step. Do not promise a bonus, eligibility, or a payout date.

## Mandatory banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

A referral-status lookup is account-specific service. Before disclosing non-public referral details or taking an action, verify that the requester is the account owner. Obtain two customer-provided identity fields from date of birth, email, phone number, and address; compare them with the user record; obtain the current timestamp using `get_current_time`; and call `log_verification` with the complete user-record fields and that timestamp. A user ID alone is not identity verification. Do not treat values merely retrieved from the user record as customer-provided confirmation.

If the execution context already contains a valid, logged verification for this same customer and inquiry, do not repeat it. If verification cannot be completed, provide only general program information and do not disclose referral-specific status, dates, or history.

## Workflow

1. **Clarify and identify the referral.** Ask for the referrer's user ID and, if needed, the referred card type, approximate application date, or confirmation that the customer means the most recent referral. Do not ask the customer to disclose the referred person's private account or transaction information.
2. **Meet the mandatory control.** Verify identity, authority, and ownership as described above before an account-specific lookup. This workflow is read-only: do not change referrals, issue credits, or make any account or card changes.
3. **Retrieve and select the record.** Call `get_referrals_by_user` with the verified referrer's user ID. Match an unambiguous customer-provided card/date detail. If the customer says “most recent,” select the record with the latest record date; if dates tie or the date is missing, ask a clarifying question rather than guessing.
4. **Assess the record.** Supply normalized record data to `scripts/assess_referral.py`, or apply the same decision rules manually. The helper only analyzes supplied data; it neither accesses bank systems nor performs an action.
5. **Explain the result in customer-friendly language.** State the selected card type and visible referral status. Separate facts in the record from program requirements and from anything that cannot be determined. Do not infer that a record date is the account-opening date, and do not infer qualifying spend from the customer saying the friend has used the card.
6. **Apply only supported program conditions.** State a card-specific condition only for a documented product:
   - **Silver Rewards Card:** 75 for each successful referral; approval plus at least $750 spent within 60 days of account opening; bonus typically posts one to two billing cycles after that requirement; up to seven referral bonuses per calendar year.
   - **Platinum Rewards Card:** $100 for each successful referral; approval plus at least $1,500 spent within 90 days; bonus typically credited after those conditions; up to seven per calendar year; self-referrals and duplicate applications do not qualify.
   - **EcoCard:** 50 for each successful referral; approval plus at least $500 spent within 60 days; bonus typically posts one to two billing cycles after that requirement; up to seven per calendar year.
   - **Any other card:** Do not invent requirements, amount, or payout timing. Explain that its active card-specific offer must be confirmed.

   Across credit card types, no more than two successful referral bonuses may be received in a rolling seven-day window. Record dates alone, especially without timestamps and final bonus-posting data, are insufficient to conclude that the rolling cap caused a denial.
7. **Give an appropriate next step.**
   - `IN_PROGRESS`: Explain that approval or card use alone does not show that all qualifying conditions are complete. State the documented spend/time condition only when the selected card is documented; otherwise, confirm that card's active offer and qualifying-spend condition. The referrer can monitor referral status.
   - `COMPLETE`: Explain that the referral is marked complete, but do not equate it with a known qualifying-spend date or actual bonus posting. For Silver or EcoCard, a bonus typically posts one to two billing cycles after qualifying spend, not necessarily after the record date. For Platinum, no precise posting window is documented. If a posting review is needed, do not manually credit anything; direct the customer to normal support to review the offer, qualifying-condition record, and posting status.
   - `REJECTED`: State that the record is rejected, but do not claim a reason unless an authoritative reason is present. The rolling seven-day cap is one possible general restriction, not a conclusion from a status alone.
   - `ERROR` or an unavailable/contradictory record: Explain that the status cannot be reliably resolved in the available system and transfer to a human agent with reason `technical_system_error`, summarizing the verified customer, referral identifier if known, observed status, and checks completed.
8. **Close safely.** Offer general referral-program information or referral-status tracking. If the customer explicitly requests a person, use `transfer_to_human_agents` with `customer_requests_human_no_specific_reason` unless a more specific supported reason applies. Never expose another person's account details, transactions, qualifying-spend total, or private application information.

## Using the helper

Run the helper with JSON on standard input:

```json
{
  "referrals": [
    {"referral_id": "string", "referred_account_type": "Silver Rewards Card", "referral_status": "IN_PROGRESS", "date": "MM/DD/YYYY"}
  ],
  "selection": {"mode": "most_recent"}
}
```

`selection.mode` is either `most_recent` or `referral_id`. For `referral_id`, include `selection.referral_id`. The script emits JSON containing a selected record, supported conditions, safe talking points, and data gaps. It rejects malformed input, unknown selection modes, no matching records, and ambiguous latest records. Treat its output as drafting assistance, not as proof of account opening, approval, spend, a bonus posting, or cap eligibility.

Example runnable call in a compatible runtime:

```sh
python3 scripts/assess_referral.py <<'JSON'
{"referrals":[{"referral_id":"example","referred_account_type":"Silver Rewards Card","referral_status":"IN_PROGRESS","date":"01/15/2030"}],"selection":{"mode":"most_recent"}}
JSON
```

Validate before responding that the selected record matches the customer's stated referral; the response does not claim unobserved spend, account-opening, successful-bonus, or posting data; card-specific claims match the selected documented product; and no account-changing tool has been called.
