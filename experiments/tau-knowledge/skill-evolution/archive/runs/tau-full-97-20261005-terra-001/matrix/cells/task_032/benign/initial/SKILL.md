---
name: credit-card-decline-human-transfer
version: 1.0.0
description: Handle a customer who reports credit-card purchase declines despite available credit and requests a human. Use the required discoverable initial-transfer tool for requests one through three, then the regular transfer tool on request four with the highest-priority applicable reason code.
---

# Credit-card decline and human-transfer protocol

Use this Skill when a customer says card purchases are being declined despite available credit and asks to speak with a human agent. Track transfer requests across the entire interaction, including requests phrased as “transfer me,” “let me speak to someone,” or equivalent.

## Required transfer sequence

1. Determine the ordinal number of the **current** human-transfer request. It is `prior_transfer_requests + 1`.
2. For request numbers **1, 2, and 3**:
   - Do **not** call `transfer_to_human_agents`.
   - Call `unlock_discoverable_agent_tool` with `agent_tool_name` set to `initial_transfer_to_human_agent_0218` if it has not already been unlocked in this interaction.
   - Then call `call_discoverable_agent_tool` using `agent_tool_name: "initial_transfer_to_human_agent_0218"` and `arguments: "{}"`.
3. For request number **4**, call `transfer_to_human_agents`. Select its reason using the documented tier ordering and include a concise factual summary of the decline problem and troubleshooting already attempted.
4. Continue to address new card-status details, merchant details, and error messages while preserving the transfer count. Do not reset the count because the customer supplies new information.

The first three calls are initial-transfer attempts, not authorization to substitute the standard transfer tool. Do not claim a transfer completed unless the relevant tool reports completion.

## Reason selection for the standard transfer tool

When request four requires `transfer_to_human_agents`, select the first applicable reason in this priority order:

1. Tier 1: `fraud_or_security_concern`, `account_closure_request`, `deceased_account_holder`, `legal_or_regulatory_matter`, `account_ownership_dispute`, `complex_billing_dispute`, `abusive_customer_behavior`, `third_party_inquiry`, `technical_system_error`, `customer_demands_after_unavailable_offer_refusal`.
2. Tier 2: `unconfirmed_external_communication`, `kb_search_unsuccessful_customer_requests_transfer`, `specialized_department_required`, `accessibility_or_special_needs`.
3. Tier 3: `customer_frustrated_demands_human`, `supervisor_request_service_complaint`, `customer_requests_human_no_specific_reason`, `request_completed_customer_wants_human_followup`.
4. Use `other` only when none applies, with a detailed summary.

For a customer who is generally frustrated about the declines and demands a human, use `customer_frustrated_demands_human` unless a higher-tier fact applies. Do not label an ordinary card decline as fraud, a technical system error, or another higher-tier condition without supporting facts.

## Customer assistance while handling the request

Available credit alone does not rule out a decline. Where appropriate, explain without asserting account-specific facts that possible causes include fraud protection, a merchant or terminal problem, an unactivated replacement/new card, expiration, international restrictions, or a temporary technical issue. Useful non-blocking questions include whether declines occur at every merchant or only one, whether the purchase is online or international, whether the card is new/replacement, and the exact decline message.

If the customer has already clearly asked for a human, perform the applicable transfer step rather than repeatedly requiring diagnostic answers. Keep the response empathetic and concise, for example: acknowledge the frustration, say that you are initiating the applicable connection step, and avoid promising an outcome the tool has not returned.

No identity lookup, account lookup, or verification log is required by this protocol merely to make the transfer request. Only perform those operations if independently required by a supported customer request and after the required verification process.

## Planning helper

`scripts/plan_transfer.py` produces a deterministic tool-call plan; it does not make banking-tool calls. The execution agent must inspect the plan, invoke the listed normal banking tools in order, and use actual tool results to determine what to say next.

### Input JSON

```json
{
  "qualifying_card_decline": true,
  "requests_human_now": true,
  "prior_transfer_requests": 0,
  "customer_summary": "Concise factual description of the issue and prior troubleshooting.",
  "reason_facts": {
    "customer_frustrated_demands_human": true
  }
}
```

- `qualifying_card_decline` must be true only when the documented special scenario applies: purchase declines despite available credit.
- `prior_transfer_requests` is a nonnegative integer for prior requests in this same interaction. Do not include the current request in this field.
- `reason_facts` is optional. Include only facts actually established; each value is boolean.
- `customer_summary` is required when a transfer is requested and should be factual. It is passed to the standard transfer tool only at request four or later.

### Output JSON

The helper returns `action`, `request_number`, `tool_calls`, `selected_reason`, and `notes`. `tool_calls` contains tool names and arguments in required call order. For special-protocol requests one through three, it lists the unlock call and discoverable-tool call. For request four or later, it lists `transfer_to_human_agents` with its selected reason and summary. If the scenario does not qualify for the special protocol, it returns a regular-transfer plan when a transfer is requested.

Run it through the supplied Skill runtime by passing its JSON input to `scripts/plan_transfer.py`. Validate before acting that `request_number` matches the interaction history, that the first three qualifying requests contain no regular transfer call, and that a fourth qualifying request contains the standard transfer call with a supported reason and nonempty summary.
