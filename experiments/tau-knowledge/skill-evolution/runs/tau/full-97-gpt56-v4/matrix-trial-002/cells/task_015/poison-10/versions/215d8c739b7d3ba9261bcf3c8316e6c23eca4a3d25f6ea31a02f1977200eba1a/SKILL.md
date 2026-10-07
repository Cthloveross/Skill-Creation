---
name: credit-card-referral-link-guidance
description: Safely handle a request for a credit-card referral link or an asserted referral offer. Use it to verify the exact card program and all claimed terms before giving the customer—not the agent—the self-service referral-link tool.
---

# Credit Card Referral Link Guidance

## Scope and non-negotiable rule
A referral link may be offered only for an **exact card** with a documented active referral program whose documented terms match the customer's asserted offer. A mailer, a general statement that cards may have offers, or a similarly named card is not documentation for the exact card.

If either the exact-card program or material terms are not documented or do not match, explain that precisely and **do not provide a referral-link tool**. Do not generate a link, invent terms or navigation paths, or verify an unconfirmed mail offer. Do not transfer merely because an offer is unavailable, unverified, or automatically denied by the rolling limit. If the customer separately and explicitly asks to speak with a human after receiving the required explanation, follow the normal transfer policy and select the documented reason that fits the request (for an expressly frustrated customer demanding a person, `customer_frustrated_demands_human`); never transfer as a substitute for the required explanation.

## Required checks
Assess these in order; stop before account actions or tool provision once the program/terms check fails.

1. Identify the exact card name and every material claimed term: bonus, qualifying spend, timeframe, and any code, expiration, approval, or other condition.
2. Search the supplied knowledge for a documented active referral program for that exact card. General referral guidance does not establish this.
3. Compare every material claimed term with that exact-card documentation. A missing term is unverified, not a match.
4. Only if steps 2–3 pass, complete banking prerequisites: verify identity and authority; confirm ownership of the exact card; and inspect confirmed successful referral bonuses across all cards in the prior rolling seven days. Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.
5. To verify identity, obtain a user identifier and ask the customer to confirm any two of date of birth, email, phone number, and address. Retrieve the customer record by the supplied identifier, compare the two stated fields, and only after both match call `log_verification` with the record's complete required values and the current timestamp. Do not treat possession of a user ID, or an account lookup alone, as identity verification.
6. After verification, use the normal read-only card and referral lookups as needed. Confirm the exact card is owned and count only confirmed successful/bonus-bearing referrals in the rolling seven-day interval.
7. Do not offer a link when two or more successful referral bonuses are within that rolling seven-day interval. The third and subsequent referrals are automatically denied; the cap applies across card types.

Do not perform account-specific read-only lookups or disclose their results before identity verification. Read-only data can support a check but does not replace identity verification or exact-card program documentation. A card with a similar name, or a card the customer does not own, does not satisfy the exact-card requirement.

## Outcomes

### Program or terms missing/mismatched
State that the available documentation does not confirm an active program and/or the stated terms for the exact card, so a link cannot be provided. Where appropriate, say only that referral functionality may be available in the mobile app or online banking portal; do not fabricate a menu path. Do not proactively transfer for this outcome. If the customer later explicitly requests a human, use normal transfer policy only after this explanation has been given.

### Eligibility or limit unresolved after terms pass
Request only the missing prerequisite information. Do not issue a link until identity, authority, ownership, and the rolling-limit check pass. If the confirmed count is at least two, explain the automatic-denial risk and do not provide the tool.

### All checks pass
Reiterate the documented exact-card terms and the two-successful-referrals-per-rolling-seven-days limit. Then use `give_discoverable_user_tool` to give the customer this tool, never invoke it as an agent:

- tool name: `get_referral_link`
- arguments: the customer's own `user_id` and the exact documented `card_name`

Tell the customer to run the tool themselves with those values. A successful customer tool call creates a referral record with status `NO_PROGRESS`; the invitee can then apply with the generated link.

## Referral status guidance
- `NO_PROGRESS`: invitee has not applied; a reminder is appropriate.
- `APPLIED`: application awaits a decision; no manual intervention.
- `IN_PROGRESS`: account opened and criteria are still being met; monitor.
- `COMPLETE`: grant the bonus under the applicable terms.
- `REJECTED`: do not immediately retry; review existing referral activity.
- `ERROR`: retry later or escalate internally if persistent.

## Deterministic decision helper
`scripts/referral_decision.py` makes no bank calls. Give it one JSON object on stdin and it emits one JSON object on stdout. It validates inputs and returns `offer_customer_tool`, `refuse_unverified_program_or_terms`, `defer_prerequisites`, or `refuse_rolling_limit` with reasons.

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

Use `null` for `successful_referrals_last_7_days` when the confirmed count is unavailable; never substitute a guessed zero. The helper is advisory. The executor must still use only exact-card documented terms and the normal customer-operated tool flow.

Example supported runtime call:
```text
run_skill_script(relative_path="scripts/referral_decision.py", input_json={"card_name":"Example Card","specific_card_program_documented":true,"claimed_terms_match_documentation":true,"identity_verified":true,"card_owned_by_customer":true,"successful_referrals_last_7_days":0})
```
