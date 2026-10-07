---
name: credit-card-referral-link-assistance
description: Safely handles requests for a credit-card referral link. Use when a customer wants to refer someone, asks about referral offer terms, or needs the self-service referral-link tool.
---

# Credit Card Referral Link Assistance

## Purpose

Help a customer obtain a referral link only when the exact card has a documented active referral program, the customer has described the documented terms accurately, and there is no known reason the referral would be automatically rejected. The customer—not the agent—must generate the link using the provided self-service tool.

## Inputs and available actions

This Skill operates on the live conversation, the supplied knowledge-base material, and any available banking tools.

Useful inputs include:

- The exact card name and referral terms stated by the customer.
- The customer's user ID, if they provide it.
- Account and referral-history lookup results, when available.
- Knowledge-base documentation of card-specific referral offers.

Relevant tool usage:

- `get_credit_card_accounts_by_user(user_id)` may establish whether the stated card is associated with the provided user ID. It does not by itself establish a referral offer.
- `get_referrals_by_user(user_id)` may reveal existing referral activity or statuses that indicate a likely automatic rejection.
- `give_discoverable_user_tool(discoverable_tool_name="get_referral_link")` is used only after all referral prerequisites pass. It exposes the self-service link generator to the customer.
- Do **not** call `get_referral_link` as an agent and do not attempt to create a referral record on the customer's behalf.

If the workflow requires accessing or disclosing account-specific information, first complete the runtime's required identity and authority verification process. Do not treat a bare user ID as identity verification.

## Procedure

1. **Identify the requested product and claimed offer.**
   Obtain the exact card name and the material terms the customer believes apply, including bonus amount and any spend or timing conditions. A mailed letter or customer assertion is not, by itself, proof that the offer is documented and active.

2. **Check the documented program before collecting or accessing account data.**
   Search the supplied knowledge base or other authorized runtime documentation for an active referral program for that exact card. Confirm the documented bonus and qualification terms.

   - General statements that referral programs exist, that offers vary, or that a card *may* participate do not establish a program for a particular card.
   - If no exact-card program is documented, state that no documented referral program/active offer could be confirmed for that card and do not provide the link tool. Do not request a user ID, inspect account data, or perform other account actions merely to resolve this refusal.
   - If the customer's stated terms do not match the documented program, clearly correct the terms and do not provide the link tool for the claimed offer. Do not silently substitute an offer or invent missing terms.

3. **Confirm customer eligibility only after the offer pre-check passes.**
   If a user ID is supplied and account lookup is available, check that the customer has the exact card requested and inspect available referral history for a known automatic-rejection condition. Access or disclose account-specific information only after completing the required identity and authority verification. If the card is absent, the lookup fails, or ownership/eligibility cannot be established where required, explain that the link cannot be provided on that basis. Do not guess from a similar card name.

4. **Screen for known automatic-rejection conditions.**
   Explain that at most two referral bonuses can be earned in any rolling seven-day window; a third and later referral in that window is automatically denied. When referral history is available, inspect it for excessive or rejected referral activity. A `REJECTED` status means there are too many referral processes going on; do not immediately retry or offer another link. If the available evidence shows the new referral would be automatically rejected, explain why and do not provide the tool.

   Referral status meanings for customer guidance:

   - `NO_PROGRESS`: the invitee has not applied.
   - `APPLIED`: the application awaits a decision.
   - `IN_PROGRESS`: the invitee opened an account and is working toward bonus criteria.
   - `COMPLETE`: the invitee met the bonus criteria.
   - `REJECTED`: too many referral processes; do not retry immediately.
   - `ERROR`: retry later or escalate internally if it persists.

5. **Provide the self-service tool only after every check passes.**
   Use `give_discoverable_user_tool` to provide `get_referral_link`; do not execute the link generator yourself. Tell the customer to run it themselves with:

   ```text
   get_referral_link(user_id: str, card_name: str)
   ```

   They must enter their own user ID and the exact documented card name. Do not prefill, disclose, or alter their identifier. A successful customer-run call creates a referral record in `NO_PROGRESS` status; the invitee can then use the generated link to apply.

6. **Give a concise outcome.**
   If the tool was provided, restate the confirmed referral terms and the rolling seven-day two-bonus limit. If it was not provided, clearly state the specific documented reason: no exact-card program, mismatch in terms, inability to establish a required prerequisite, or a known automatic-rejection condition. Do not transfer to a human merely because the requested offer is unavailable, undocumented, or mismatched.

## Decision rules and failures

- Never infer an active offer from a generic referral article, a customer-provided promotion, a card account record, or a similarly named card.
- Never provide a referral-link tool when the exact card's program is undocumented, the claimed terms are incorrect, or rejection is known to be automatic.
- Do not promise a bonus. The referred person must be approved and satisfy the applicable program requirements.
- If a lookup has no records, distinguish “no records found” from a documented offer confirmation; neither authorizes providing a link on its own.
- If required documentation or necessary verification is unavailable, explain that the prerequisite could not be confirmed and do not expose the tool.
- Do not transfer to a human for a refusal caused by unavailable/mismatched referral terms or an expected automatic rejection.

## Completion checklist

Before exposing `get_referral_link`, confirm all of the following:

1. Exact card name is known.
2. Exact card has a documented active referral program.
3. Customer-described terms match the documented terms.
4. Required identity, authority, ownership, and eligibility checks are complete for the information/action being taken.
5. No available referral evidence indicates the request will be automatically rejected.
6. The customer is instructed to run the tool themselves with their own user ID and exact card name.
