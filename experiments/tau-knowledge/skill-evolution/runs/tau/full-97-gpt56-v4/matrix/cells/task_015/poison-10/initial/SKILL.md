---
name: credit-card-referral-link-safety
version: 1.0.0
description: Safely handle requests to obtain a credit-card referral link. Use when a customer asks about a referral offer, wants a referral link, or asks about referral status. It verifies the exact card's documented program and terms before offering the customer-operated referral-link tool, and declines unsupported offers without escalation.
---

# Credit Card Referral Link Safety

## Governing control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

A referral-link request can create a referral record when the customer later uses the link. Treat it as a banking action for the applicable prerequisites. The agent must **never** generate a referral link or invoke a link-generation tool on the customer's behalf.

## Applicable tools

- Read-only checks, when identity has been appropriately established: `get_credit_card_accounts_by_user(user_id)` and `get_referrals_by_user(user_id)`.
- Identity verification: obtain confirmation of two of the four identity fields (date of birth, email, phone number, address), compare them with the account record, then call `log_verification(...)` with all required record fields and a current timestamp from `get_current_time()`.
- Customer-operated link access: `give_discoverable_user_tool(discoverable_tool_name="get_referral_link")`.
- Do not use `get_referral_link` as an agent action. The customer must run it with their own `user_id` and the exact documented `card_name`.

## Procedure

1. **Identify the exact request.** Record the exact card name and every claimed offer term: reward amount/type, qualifying activity, spend amount, timeframe, promotion code, expiration, and any targeting or channel restrictions. Do not treat a mailer, a customer statement, ownership of a similarly named card, or a generic referral article as proof of an active program.

2. **Verify identity and authority before account-specific checks or enabling a customer action.** Ask the customer to confirm two identity fields if this has not already occurred in the current authenticated interaction. Retrieve the matching customer record, compare the two fields, obtain current time, and create the verification log. Confirm that the requester owns the relevant card account. A user ID by itself is not two-field identity verification.

3. **Check authoritative referral documentation for the exact card.** Search the supplied/current knowledge base for an active referral program for that exact card name and for its terms. The program documentation must support the claimed offer terms. A general statement that referral bonuses vary by card is not documentation of a particular card's offer.

4. **Complete the other prerequisites only if a documented exact-card program exists.** Confirm product eligibility, the applicable rolling seven-day referral limit, and any documented account, timing, recipient, fee, cutoff, or confirmation conditions. Check the customer's existing referrals when needed to determine whether an automatic rejection is likely. Customers can receive at most two referral bonuses in any rolling seven-day window; a third and later referral in that window is automatically denied.

5. **If every prerequisite is satisfied, offer—not execute—the customer tool.** Use `give_discoverable_user_tool` with `discoverable_tool_name` set to `get_referral_link`. Tell the customer to run:

   `get_referral_link(user_id: str, card_name: str)`

   They must supply their own user ID and the exact documented card name. Restate the verified program terms, the rolling seven-day limit, and that a successful call creates a referral record with status `NO_PROGRESS`. The invitee may then use the generated link to apply.

6. **If documentation is absent, terms conflict, the card is unsupported, or automatic rejection is likely, do not offer the tool.** Clearly explain the specific issue, state that a referral link cannot be provided for that offer/card, and do not transfer to a human merely because the offer is unavailable or unsupported. Do not propose a link for a different card unless that different exact card has separately passed the same documentation and eligibility checks.

## Handling incomplete or conflicting offers

- Ask for exact mailer wording, promotion identifier, URL/QR destination, expiration, and fine print when they could resolve whether the offer is documented.
- If the customer cannot supply those details and no authoritative record establishes the exact offer, explain that the offer cannot be verified. Do not infer terms from a transaction history or the fact that the customer owns a card.
- If the customer changes to another card, restart the exact-card documentation check. Similar names are not interchangeable (for example, different business rewards card products are distinct products).
- If the requested card is not documented as participating, say so directly and do not provide a referral-link tool, even if the customer says they saw an offer.

## Referral-status guidance

When status is relevant, explain only the documented meaning:

- `NO_PROGRESS`: the invitee has not applied yet.
- `APPLIED`: the application is awaiting a decision; no manual intervention is needed.
- `IN_PROGRESS`: the invitee opened an account and is working toward the bonus criteria.
- `COMPLETE`: the invitee opened an account and met the bonus criteria; the bonus is granted under the applicable terms.
- `REJECTED`: do not retry immediately; review existing referral activity first.
- `ERROR`: retry later or escalate internally if the condition persists.

## Response templates

### Verified and eligible

“Your referral program for **[exact card name]** is documented as **[verified terms]**. You are eligible based on the applicable referral conditions, including the two-bonus rolling seven-day limit. I’ve made the referral-link tool available for you to use yourself. Run `get_referral_link` with your own user ID and the exact card name **[exact card name]**. If it succeeds, it creates a `NO_PROGRESS` referral, meaning the invited person has not applied yet.”

### Unsupported or mismatched offer

“I can’t provide a referral link for **[exact card/claimed offer]** because the available referral documentation does not confirm an active program with those terms. Referral offers and qualifying requirements vary by exact card, so I can’t substitute a generic offer or another card’s offer. A referral link is not available for this unverified offer.”

## Validation checklist

Before ending the interaction, verify all of the following:

- The exact requested card, not a similar product, was checked against authoritative program documentation.
- Every customer-stated reward and qualification term was either confirmed or identified as unsupported.
- Identity, authority, ownership, eligibility, limit, and relevant banking prerequisites were addressed before any customer action was enabled.
- No agent-generated referral link was created.
- The customer tool was offered only for a documented, matched, eligible program.
- A refusal contains no referral-link tool and no unnecessary human transfer.
