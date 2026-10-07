---
name: external-offer-verification-transfer
description: Handle a customer who wants to redeem a promotion shown in a mailed flyer, letter, email, or other external communication when the offer cannot be verified against available knowledge. Select the highest-priority applicable human-transfer reason and prepare a safe handoff.
---

# External Offer Verification and Handoff

Use this Skill after reviewing the available knowledge for the claimed offer. It is intended for external promotions that cannot be located or confirmed, not for ordinary questions about documented card benefits.

## Method

1. Identify the claimed external communication and request the exact product/card name, offer or claim code, and promotion/expiration dates. Do not infer missing terms from a customer description.
2. Check the available knowledge for an exact matching offer and its redemption or application path.
3. Do not promise enrollment, redemption, eligibility, statement credits, or a promotional fee term unless the exact offer is verified.
4. Apply transfer reasons by tier, choosing the highest applicable tier:
   - If a Tier 1 situation applies, use its specific reason. In particular, use `customer_demands_after_unavailable_offer_refusal` only when the customer was told an unavailable offer is not available, persisted multiple times, and now demands a human.
   - Use `unconfirmed_external_communication` when the customer claims a specific flyer/letter/email/program offer and it cannot be verified after knowledge review. This applies even if the customer has not supplied enough flyer details to identify it.
   - Use Tier 3 reasons only if no Tier 1 or Tier 2 reason applies.
5. Before transferring, explain briefly that the specific external offer cannot be verified from the currently available information and that it will be reviewed. Do not characterize an ongoing documented card feature as proof of an unverified time-limited flyer promotion.
6. Call `transfer_to_human_agents` with the selected reason and a factual summary. The executor, not this Skill or its script, performs the transfer.

No identity lookup or verification is needed merely to transfer an unverified external-offer inquiry. Do not search for a customer account without a user-provided identifier and a task need.

## Current-case application

When the conversation establishes that a flyer offer cannot be matched to documented offers after review, and the customer cannot provide the card name, code, or dates needed to resolve it, transfer using `unconfirmed_external_communication`. Include in the summary that the offer came from an external communication, which identifiers are missing, what was checked, and that no redemption was completed. Avoid including unnecessary personal data.

## Helper

`scripts/select_transfer.py` makes a deterministic recommendation from a JSON conversation state. It does not search a knowledge base or perform any banking action.

### Input JSON

```json
{
  "external_offer_claimed": true,
  "kb_search_performed": true,
  "offer_verified": false,
  "offer_identifiers_provided": false,
  "customer_requested_human": false,
  "higher_priority_reason": null,
  "offer_source": "flyer",
  "offer_description": "optional customer-described terms",
  "clarifications": [{"question": "...", "result": "..."}]
}
```

All fields are optional. `clarifications` may be used instead of the Boolean fields; the helper recognizes plainly stated flyer/letter/email claims and statements that the offer could not be identified or did not match documented offers. Set `higher_priority_reason` only to a valid applicable Tier 1 reason.

### Output JSON

The script emits one object with:

- `decision`: `transfer` or `request_more_information`
- `reason`: an allowed transfer reason or `null`
- `summary`: ready to pass to `transfer_to_human_agents` when `decision` is `transfer`
- `customer_message`: a safe next message
- `validation`: facts used and any missing prerequisite

Example invocation by an executor:

```text
run_skill_script(relative_path="scripts/select_transfer.py", input_json={"external_offer_claimed": true, "kb_search_performed": true, "offer_verified": false, "offer_identifiers_provided": false})
```

Validate that `decision` is `transfer`, `reason` is `unconfirmed_external_communication` unless a valid higher-tier reason applies, and the summary accurately reflects the actual conversation. Then make the normal `transfer_to_human_agents` tool call using that output. If the helper returns `request_more_information`, ask for the requested flyer identifiers and complete the knowledge review instead of transferring on this reason.
