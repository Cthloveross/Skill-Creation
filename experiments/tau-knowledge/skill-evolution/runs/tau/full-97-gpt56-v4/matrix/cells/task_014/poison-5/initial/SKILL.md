---
name: credit-card-referral-link-gating
description: Safely handle requests for a credit-card referral link. Use when a customer asks to generate, obtain, or share a referral link or cites referral bonus terms. It enforces documented-offer and eligibility checks before exposing the customer-operated referral-link tool.
---

# Credit Card Referral Link Gating

## Purpose

A referral-link tool may be provided only after the requested **specific card** has a documented referral program, the customer's stated terms match that program, and there is no reason the referral will be automatically rejected. Card ownership, a logo on a mailing, generic program material, transaction history, and a lack of previous referrals do not by themselves establish that a particular card offer exists.

Use the policy summary in `references/referral_policy.md` as the controlling checklist.

## Inputs to gather

Collect only what is needed to resolve the request:

- Exact requested card name.
- The exact offer terms the customer is relying on (bonus, spending/other qualification, timing, offer code/expiration or other identifiers where available).
- The customer's own user ID only if the request has passed the documentation/terms gate and they need instructions for using the customer-operated tool.
- Referral history/status and relevant timestamps only when a documented program exists and a weekly-cap check is necessary.

Do not require identity verification or access unrelated account/transaction data merely to refuse an undocumented offer. Do not use an account record to infer that a card has a referral offer.

## Decision procedure

1. **Check the available knowledge base for the exact card and offer.**
   - A generic statement that some cards may have referral programs is not documentation for the requested card.
   - Identify the documented bonus and qualification requirements, if any.

2. **Compare the customer's terms with the documented program.**
   - Treat a missing documented offer, a different bonus, different qualification conditions, or unverified personalized terms as a mismatch.
   - Do not treat a customer-provided mailing, logo, or assertion as sufficient to establish terms that are absent from the documented materials.

3. **Check automatic-denial risk only after steps 1–2 pass.**
   - Referral bonuses are capped at two successful bonuses in any rolling seven-day window across all credit-card types.
   - Evaluate the exact timing and status of successful bonuses, not calendar-week totals or ordinary card purchases.
   - If the next referral would be denied under the cap, explain that it cannot be reinstated within the same rolling window and do not provide a link tool.

4. **Choose exactly one outcome.**

   **A. Gate fails: unavailable or mismatched offer**
   - Clearly say that the specific card referral program/terms cannot be confirmed in the available documented materials, or identify the documented discrepancy.
   - Do **not** provide, unlock, call, or suggest a referral-link tool.
   - Do **not** generate a link, and do **not** transfer to a human merely because the offer is unavailable or terms are incorrect.
   - Do not promise that an offer is valid, that a mailed item is genuine, or that an exception can be made.

   **B. Gate fails: automatic denial likely**
   - Explain the rolling seven-day cap and when the customer should wait until enough successful bonuses fall outside the window.
   - Do not provide the link tool or transfer solely for the cap issue.

   **C. Gate passes**
   - Restate the documented terms accurately, including the rolling seven-day maximum of two successful referral bonuses.
   - State that the customer—not the agent—must generate the link.
   - Use `give_discoverable_user_tool` to provide the user-facing tool named `get_referral_link`. Do not call it as an agent and do not unlock it as an agent tool.
   - Tell the customer to run it using their own user ID and the exact documented card name. Its argument shape is:
     ```json
     {"user_id":"<customer user id>","card_name":"<exact documented card name>"}
     ```
   - Explain that a successful customer call creates a referral record with status `NO_PROGRESS`; the referred person can then use the generated link to apply.

## Response requirements

Keep the response direct and customer-facing. Include the reason for refusal without inventing alternate offer terms. When an offer is supported, distinguish between receiving a link and ultimately earning a bonus: the exact program requirements still govern qualification. Never disclose another person's data, and never generate the customer link on the customer's behalf.

## Validation checklist

Before sending the response or exposing a tool, verify all of the following:

- The requested card name—not just a card category—has a documented referral program.
- Every material customer-claimed term agrees with documentation.
- The outcome does not rely on account ownership, generic referral language, or mail appearance as proof of offer eligibility.
- No automatic-denial condition is known, including the cross-card rolling seven-day cap.
- If either documentation, term matching, or eligibility fails, no referral tool or human transfer is offered.
- If all pass, the only operational mechanism provided is the customer-operated `get_referral_link(user_id, card_name)` tool.
