---
name: credit-card-referral-link
summary: Safely handle requests for a credit-card referral link by confirming the exact card's documented offer and terms, checking automatic-denial risk, and—only when eligible—giving the customer the self-service referral-link tool.
---

# Credit-Card Referral Link

Use this Skill when a customer asks to obtain, use, or clarify a referral link for a credit card.

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

Apply the applicable prerequisites before accessing customer-specific referral records or enabling a customer-specific action. The agent must never generate a referral link on the customer's behalf.

## Required decision process

1. **Identify the exact card and the claimed offer.** Capture the exact requested card name and each material claimed term, including the referrer bonus, referred person's qualifying activity, amount, and timeframe. A mailer or customer statement is not by itself confirmation that an active offer is documented.
2. **Search the knowledge base before offering a link mechanism.** Find documentation for the specific card, not merely general referral-program information. Confirm that the card has an active documented referral program and record the exact documented card name and terms.
3. **Compare terms.** Verify that every material term the customer cited agrees with the documented program. If the documentation lacks a claimed term, cannot establish the card's participation, or conflicts with the customer's claim, treat the terms as unconfirmed or incorrect.
4. **Assess automatic-denial risk.** The program permits at most two referral bonuses in a rolling seven-day window; third and subsequent referrals in that window are automatically denied. After applicable identity, authority, and ownership verification, inspect the customer's referral information when necessary and determine whether two qualifying bonuses have already occurred in the preceding seven days. Do not infer a qualifying status or completion timestamp from an undocumented tool response. If the count or timing cannot be determined, do not treat automatic-denial risk as cleared.
5. **Make the decision.** Use `scripts/evaluate_referral_request.py` to consistently classify the referral-policy decision after the factual checks above. The script does not search the knowledge base, verify identity, access customer records, or make a banking action.

## When not to provide the tool

Do **not** provide a referral-link tool if any of the following applies:

- no active referral program is documented for the exact requested card;
- the customer's claimed terms conflict with, or cannot be confirmed by, the documented terms;
- there is reason to believe the referral would be automatically denied, including two qualifying referral bonuses in the relevant rolling seven-day window; or
- a required factual check remains unknown.

Explain the specific documented gap, mismatch, or limit concisely. Reiterate only the actual documented terms when available. Do not transfer the customer to a human solely because the offer is unavailable, undocumented, mismatched, or expected to be automatically denied.

## Providing the self-service mechanism

Only after all checks pass:

1. State the exact documented terms and remind the customer of the rolling seven-day maximum of two referral bonuses.
2. Use `give_discoverable_user_tool` to provide (not execute) the discoverable tool named `get_referral_link`.
3. Tell the customer to run it themselves with their **own** `user_id` and the exact documented `card_name`:
   `get_referral_link(user_id: str, card_name: str)`.
4. Do not call the referral-link tool, unlock an agent equivalent, or submit the customer's identifiers on the customer's behalf. A successful customer-run call creates a referral record with status `NO_PROGRESS`; the referred person may then use the generated link to apply.

Do not promise a bonus merely because a link is created. Eligibility and the weekly limit still govern referral bonuses.

## Helper script

Run the policy helper with JSON on stdin:

```json
{
  "documented_program_found": true,
  "documented_card_name": "Exact documented card name",
  "terms_match": true,
  "automatic_rejection_risk": false,
  "qualifying_bonus_count_last_7_days": 0
}
```

Example invocation through the packaged runtime is `run_skill_script` with `relative_path` set to `scripts/evaluate_referral_request.py` and the object above as `input_json`.

The script emits JSON. `decision: "provide_user_tool"` means only that the referral-policy checks represented by its input passed; the executor must still ensure the mandatory banking controls and use the self-service procedure above. Any `refuse` or `needs_information` decision means do not provide the tool. Validate that the output has `ok: true`, a recognized decision, and nonempty `reasons` before relying on it.
