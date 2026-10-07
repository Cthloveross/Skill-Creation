---
name: credit-card-referral-link
description: Safely handle requests to obtain, use, or clarify a credit-card referral link. Apply when a customer asks about a specific card referral offer, referral terms, a referral link, or a human transfer relating to an unsupported referral offer.
---

# Credit-Card Referral Link

Use this Skill when a customer asks to obtain, use, or clarify a referral link for a credit card.

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

Apply applicable prerequisites before accessing customer-specific referral records or enabling a customer-specific action. The agent must never generate a referral link on the customer's behalf.

## Required decision process

1. **Identify the exact card and claimed offer.** Capture the exact requested card name and all material claimed terms, such as referrer bonus, qualifying activity, amount, and timeframe. A mailer or customer statement alone does not establish that an active offer is documented.
2. **Find authoritative card-specific documentation.** Before offering a referral mechanism, search available knowledge sources for the exact card, rather than relying on general referral-program material. Confirm an active documented program and its exact documented card name and terms.
3. **Compare every material term.** Confirm that the customer's stated terms agree with the documented program. If the documentation does not establish participation or a claimed term, or conflicts with the claim, treat the offer as unconfirmed or incorrect.
4. **Assess automatic-denial risk.** The program permits at most two referral bonuses in a rolling seven-day window; third and subsequent referrals in that window are automatically denied. After applicable verification, inspect customer referral information when necessary. Do not infer qualifying status or completion time from an undocumented response. If the count or timing cannot be established, do not clear automatic-denial risk.
5. **Classify the result.** Use `scripts/evaluate_referral_request.py` after factual checks to classify the policy result consistently. The helper does not search documentation, verify identity, access records, or perform banking actions.

## Refusal for an undocumented, mismatched, or unavailable offer

Do **not** provide a referral-link tool when any of these applies:

- no active referral program is documented for the exact requested card;
- claimed terms conflict with, or cannot be confirmed by, documented terms;
- the referral may be automatically denied, including because two qualifying bonuses occurred in the applicable rolling seven-day window; or
- a required factual check remains unknown.

State the exact card name and explain the documented gap, mismatch, limit, or missing confirmation. Use clear refusal language, such as: **“I’m unable to provide a referral-link tool for the [exact card] offer because I cannot confirm an active, documented referral program and the stated terms.”** This wording accurately distinguishes a refusal from merely offering a different way to obtain a link. Do not state or imply that the offer is active, valid, or eligible based only on the customer's claim.

Do not transfer the customer to a human solely to investigate, confirm, or obtain an unavailable, undocumented, mismatched, or automatically denied referral offer. Do not suggest another human escalation route for that purpose. If the customer explicitly requests such a transfer, explicitly refuse the routing and keep the explanation tied to the unsupported referral offer, for example: **“I’m unable to transfer you for this referral offer because its active, documented program and terms cannot be confirmed.”** Do not invoke a transfer or escalation tool in this case.

Reiterate only actual documented terms when they are available.

## Providing the self-service mechanism

Only after all required checks pass:

1. State the exact documented terms and remind the customer of the rolling seven-day maximum of two referral bonuses.
2. Use `give_discoverable_user_tool` to provide, but not execute, the discoverable tool named `get_referral_link`.
3. Tell the customer to run it with their own `user_id` and the exact documented `card_name`:
   `get_referral_link(user_id: str, card_name: str)`.
4. Do not call the referral-link tool, unlock an agent equivalent, or submit customer identifiers on the customer's behalf. A successful customer-run call creates a referral record with status `NO_PROGRESS`; the referred person can then use the generated link to apply.

Do not promise a bonus merely because a link is created. Eligibility and the weekly limit still govern referral bonuses.

## Helper script

Run the policy helper with one JSON object on stdin:

```json
{
  "documented_program_found": true,
  "documented_card_name": "Exact documented card name",
  "terms_match": true,
  "automatic_rejection_risk": false,
  "qualifying_bonus_count_last_7_days": 0
}
```

Invoke it through the packaged runtime using `run_skill_script` with `relative_path` set to `scripts/evaluate_referral_request.py` and the object as `input_json`.

The script emits one JSON object with `ok`, `decision`, `reasons`, and `documented_card_name`. Validate that `ok` is `true`, `decision` is recognized, and `reasons` is nonempty before relying on it. `decision: "provide_user_tool"` only means the represented referral-policy checks passed; the executor must still follow the mandatory banking control and self-service process. Any `refuse`, `needs_information`, or `invalid_input` result means do not provide the referral-link tool.
