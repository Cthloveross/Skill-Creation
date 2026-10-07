---
name: credit-card-referral-link-eligibility
description: Assess a request for a credit-card referral link against documented, card-specific referral offers. Use when a customer asks how to obtain or share a referral link, especially when they state bonus terms.
---

# Credit-card referral-link eligibility

Use this Skill before offering the customer the referral-link tool. A referral link can be offered only when the requested **specific card** has an active, documented referral program and the customer's stated offer terms agree with that documentation.

## Required runtime inputs

Collect or locate, from the available knowledge base at execution time:

- the requested card's exact name;
- the terms the customer claims, if any; and
- card-specific referral-program documentation, including whether it is active and its terms.

General documentation that says referral offers may exist, vary by card, or are limited to two bonuses in a rolling seven-day window is **not** evidence that a particular card has an offer.

## Mandatory refusal and no-transfer rule

If the requested card has no documented card-specific referral program, the program is inactive or ambiguous, the stated terms cannot be confirmed, or the referral would be automatically rejected:

1. Tell the customer that the program or stated terms **cannot be confirmed from documentation**.
2. Clearly state that you **cannot provide a referral link**.
3. Do not call or offer `get_referral_link`, `give_discoverable_user_tool`, an agent referral-link tool, or another link-generation path.
4. **Do not call `transfer_to_human_agents`.** This prohibition still applies if the customer is frustrated, asks to escalate, asks for a supervisor, or repeats the request. Give the documented refusal rather than transferring.

An external letter or customer assertion is not card-specific program documentation by itself. Do not infer an offer or its terms from it.

## Decision procedure

1. Search the knowledge base for documentation covering the exact requested card.
2. Compare the customer's claimed terms with the documented terms. Do not infer missing terms or treat a generic referral article as a card-specific offer.
3. Use `scripts/assess_referral_offer.py` with the card, customer terms, and the documented card-program records found at runtime. The script is deliberately fail-closed: missing, inactive, ambiguous, or nonmatching documentation produces `do_not_offer_link`.
4. Follow the script's `decision`:
   - `offer_link`: Restate the documented terms and call `give_discoverable_user_tool` with `discoverable_tool_name` set to `get_referral_link`. Tell the customer to run it themselves with their own `user_id` and the exact card name. The agent must not run or generate the link on the customer's behalf. A successful customer call creates a referral record in `NO_PROGRESS` status.
   - `do_not_offer_link`: Send the script's customer-facing explanation, making sure it says both that the offer cannot be confirmed from documentation and that a referral link cannot be provided. Do not provide a link and do not transfer the customer.
5. Whenever discussing an available program, remind the customer that at most two referral bonuses can be earned in any rolling seven-day window; a third or later referral in that window is automatically denied. Also state the correct documented offer terms.

## Script interface

Run `scripts/assess_referral_offer.py` with one JSON object on stdin (or through `run_skill_script`). It emits one JSON object on stdout.

Input schema:

```json
{
  "requested_card_name": "string, required",
  "customer_claimed_terms": "string or null",
  "documented_programs": [
    {
      "card_name": "string",
      "active": true,
      "terms": "string"
    }
  ]
}
```

`documented_programs` must contain only records supported by current card-specific knowledge-base evidence. `terms` must be the documented referral terms, not a paraphrase invented by the executor. If no suitable documentation is found, pass an empty array.

Output schema:

```json
{
  "decision": "offer_link | do_not_offer_link",
  "reason_code": "documented_active_offer | no_documented_card_program | inactive_card_program | ambiguous_card_documentation | claimed_terms_mismatch",
  "matched_program": {"card_name": "string", "terms": "string"} | null,
  "customer_message": "string"
}
```

## Validation before completing the response

- Confirm the selected program record exactly identifies the requested card after case, whitespace, and Unicode-punctuation normalization.
- Confirm exactly one active card-specific record applies.
- If the customer supplied terms, ensure their normalized wording matches the normalized documented terms. If it does not, explain that the stated terms cannot be confirmed and decline to provide the link.
- Do not expose a link tool unless the script returns `offer_link`.
- On every `do_not_offer_link` result, do not transfer to a human agent, including after an escalation request.
- Do not substitute an agent tool or an app/portal path for the required customer-run `get_referral_link` tool when an eligible link is being provided.

See `references/referral_policy.md` for the governing policy distilled from the supplied documentation.
