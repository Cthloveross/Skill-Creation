---
name: credit-card-referral-link-guidance
description: Handle requests to generate or obtain a credit-card referral link. Use when a customer cites a referral offer, asks for a referral link, or asks about referral eligibility/status. It verifies that the specific card and claimed terms are documented before offering the customer-operated referral-link tool.
---

# Credit Card Referral Link Guidance

## Purpose
Determine whether it is safe to offer a customer the self-service `get_referral_link(user_id, card_name)` tool. Do not generate a link as an agent.

## Required checks
Before providing a referral link, establish all of the following:

1. **Specific-card program documentation:** Search the available knowledge for an active referral program for the exact card named by the customer. General statements that some cards may participate are not confirmation that a particular card participates.
2. **Terms match:** Compare the customer's claimed reward, spending requirement, timeframe, codes, expiration, and other conditions against the documented program. Do not treat an unverified mailed offer as documented terms.
3. **Customer/card eligibility:** Where the runtime permits and the action requires it, verify the customer's identity and authority, confirm ownership of the stated card, and review referral activity relevant to the rolling seven-day limit.
4. **Automatic-denial risk:** A customer can receive at most two referral bonuses in a rolling seven-day window across all card types. A third or subsequent referral in that window is automatically denied. Do not offer a link if the information indicates automatic rejection.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

Read-only account/referral lookups may help assess the prerequisites, but they do not substitute for documented specific-card referral terms. Do not expose private account details unnecessarily.

## Decision procedure

1. Identify the exact card and all terms the customer claims.
2. Find documentation for that exact card's referral program and compare every claimed material term.
3. If exact-card program documentation is missing, or any material claimed term is missing or conflicts, **do not provide a referral link tool**. Explain that the offer cannot be verified from the available documented program and that a link cannot be issued for unconfirmed terms. Do not transfer to a human merely because the offer is unavailable or unverified.
4. If terms are documented but required identity, ownership, or referral-limit information is unavailable, obtain the necessary information or explain that eligibility cannot yet be established. Do not issue a link until all prerequisites are satisfied.
5. If the rolling limit indicates likely automatic denial, explain the two-bonus rolling-seven-day cap and do not provide the tool.
6. Only when the exact card program is documented, terms match, and eligibility checks pass:
   - reiterate the documented terms and rolling seven-day limit;
   - use `give_discoverable_user_tool` to provide `get_referral_link` to the customer, not an agent tool;
   - instruct the customer to enter **their own** user ID and the exact documented card name;
   - never call or generate the link on the customer's behalf.

A successful customer tool call creates a referral record with status `NO_PROGRESS`; the invited person may then apply using the generated link.

## Referral status guidance
- `NO_PROGRESS`: invitee has not applied; a reminder is appropriate.
- `APPLIED`: application is awaiting a decision; no manual intervention.
- `IN_PROGRESS`: account opened and criteria are still being met; monitor.
- `COMPLETE`: referral bonus is granted under applicable terms.
- `REJECTED`: do not retry immediately; review existing referral activity.
- `ERROR`: retry later or escalate internally if persistent.

## Communication requirements
When refusing, be precise: distinguish a lack of documented exact-card program/terms from a customer eligibility failure. Do not invent app menu paths, offer details, codes, expiration dates, or bonus conditions. The general documented limit is two successful referral bonuses in any rolling seven-day period across cards. If a customer asks how to locate an option but no specific navigation path is documented, state only that the mobile app or online banking portal may offer referral functionality; do not fabricate steps.

## Optional deterministic helper
`scripts/referral_decision.py` evaluates structured check results without making banking calls. It receives JSON on standard input and emits a JSON decision on standard output.

Input schema:
```json
{
  "card_name": "string",
  "specific_card_program_documented": true,
  "claimed_terms_match_documentation": true,
  "identity_verified": true,
  "card_owned_by_customer": true,
  "successful_referrals_last_7_days": 0
}
```

`successful_referrals_last_7_days` must be a non-negative integer representing confirmed successful/bonus-bearing referrals across all card types in the relevant rolling seven-day interval. Set a prerequisite field to `false` when it is unknown rather than guessing.

Example invocation in a supported script runtime:
```text
run_skill_script(relative_path="scripts/referral_decision.py", input_json={"card_name":"Example Card","specific_card_program_documented":true,"claimed_terms_match_documentation":true,"identity_verified":true,"card_owned_by_customer":true,"successful_referrals_last_7_days":0})
```

Validate that the output has a `decision` of `offer_customer_tool`, `refuse_unverified_program_or_terms`, `defer_identity_or_ownership`, or `refuse_rolling_limit`, and follow its `reasons`. The helper is advisory; the executor must still use only documented terms and the normal customer-operated tool flow.