---
name: referral-bonus-status-explainer
description: Handle a customer inquiry about a missing credit-card referral bonus using available referral records and card-specific referral terms. Use when the agent must explain eligibility, an in-progress/rejected/complete referral status, timing, or referral caps and no referral-remediation tool is available.
---

# Referral bonus status explainer

## Scope and assumptions

Use this Skill for informational referral-status support. It does not authorize a bonus, change a referral, disclose a referred person's data, or infer facts not returned by the available records.

The available referral list is the source of truth for the referrer's record. A customer's statement that their friend was approved or has begun using a card is useful context, but does not override a returned `IN_PROGRESS`, `REJECTED`, or `COMPLETE` status.

## Inputs to inspect

1. Identify the customer and obtain their referral records with the normal banking tools, unless the public task already provides those observations.
2. Resolve which referral is at issue from the customer's clarification. Match the card type and approximate application/referral date; if ambiguity remains, ask a focused clarification before discussing a particular record.
3. Read the current time if timing must be evaluated.
4. Use the referral's card type to select the applicable terms. Do not apply another card's reward amount or qualification terms to this card.

Do not reveal unrelated referral IDs, other referrals' details, or the referred person's account information.

## Silver Rewards Card terms

For a Silver Rewards Card referral:

- The referred person must be approved and spend at least $750 within 60 days of account opening.
- The referrer earns 75 for a successful referral, subject to the program limits.
- The bonus normally posts one to two billing cycles **after** the qualifying $750 spend requirement has been met.
- A referrer can earn at most 7 referral bonuses per calendar year.
- Across all credit-card types, no more than 2 successful referral bonuses may occur in a rolling 7-day window. The window is based on exact timestamps, not calendar-week dates.

Other card types have their own card-specific bonus terms; the cross-card rolling 7-day restriction still applies.

## Reasoning procedure

1. State the matched referral's card type, date, and status in customer-friendly language, without exposing its internal identifier.
2. Interpret the status carefully:
   - `IN_PROGRESS`: qualification and processing are not complete in the record. Explain the relevant card's approval/spend requirements and that payout timing has not started until they are met. Do not say the friend failed, has not spent enough, or will be paid on a particular date unless a tool explicitly establishes that fact.
   - `COMPLETE`: the referral is shown complete. If the customer still reports no payment, explain the normal one-to-two-billing-cycle posting interval after qualification and compare only when a verified qualification date is available. If it appears overdue and no corrective tool exists, offer appropriate human follow-up rather than inventing a resolution.
   - `REJECTED`: explain that it did not qualify according to the record. If the available facts establish a limit was reached, mention that limit; otherwise do not guess why it was rejected.
   - `ERROR` or an unrecognized status: say the record needs review and transfer/escalate using the applicable supported process.
3. Consider limits only as warranted by the records:
   - Count only records that explicitly represent successful/completed referrals when assessing the annual cap. Count within the relevant calendar year.
   - Never call a rolling-7-day result definitive from date-only records, because exact timestamps are required. A nearby completed referral can be described as a possible timing constraint, not a confirmed denial reason.
   - An `IN_PROGRESS` referral is not proof that a limit has denied it. A `REJECTED` referral may be attributed to a cap only where the record or other available evidence supports that conclusion.
4. If a needed fact is unavailable (such as the referred account's opening date, qualifying spend total/date, or a payout posting), say so plainly. Do not attempt to access the referred person's information through the referrer or make up a transaction history.
5. Give the customer the practical next step: their friend must meet the card-specific requirement within the allowed period, and the customer should allow the normal posting interval after qualification. If the status is complete and that interval is demonstrably past, or an error requires review, offer human follow-up using the normal transfer tool and an accurate summary.

## Customer response pattern

Use a short, empathetic explanation such as:

> I checked the referral you identified. It is currently shown as **[status]** for the **[card type]** referral dated **[date]**. For this card, the referred person must be approved and spend at least **[threshold]** within **[period]** of opening the account. The referral bonus normally posts **[posting interval]** after that requirement is met. Because the record is not yet complete, I cannot confirm that the qualifying requirement and bonus processing have finished. Once it is complete, please allow the normal posting time. [Add only supported limit or escalation information.]

For a non-Silver card, replace the bracketed terms only with its established card-specific terms. Never promise a bonus or a posting date.

## Validation checklist

Before responding, confirm that the response:

- identifies the correct referral rather than the most recent record by assumption;
- uses the matching card's requirements;
- distinguishes record status from the customer's assertion;
- treats payout timing as beginning after qualifying spend, not merely application or approval;
- does not claim an exact rolling-window conclusion from dates alone;
- does not expose unrelated records or another person's information; and
- does not claim a payment, correction, or escalation was performed when no supported tool performed it.

## Handling unavailable remediation

The available banking tools are read/query tools for referral status and do not provide a referral-payment adjustment or status-correction action. Do not fabricate one. Where review is necessary and the user requests or needs follow-up, use the normal human-transfer mechanism with a summary stating the identified referral, its returned status, relevant timing facts, and what information is unavailable.
