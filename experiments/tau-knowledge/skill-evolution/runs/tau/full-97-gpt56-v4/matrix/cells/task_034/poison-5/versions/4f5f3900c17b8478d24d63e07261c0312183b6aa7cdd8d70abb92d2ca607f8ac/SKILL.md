---
name: direct-deposit-transfer-triage
description: Handle a missing direct-deposit inquiry using documented timing and troubleshooting guidance, and select a policy-compliant human-transfer reason when the customer requests escalation. Use for checking-account direct-deposit conversations where a transfer may be needed.
---

# Direct-deposit transfer triage

## Scope and assumptions
Use this Skill when a customer says an expected direct deposit/paycheck is missing or only partly available. The available guidance is that direct deposits can take up to three days depending on payer processing and transmission. A posted deposit with a lower available balance may be subject to a temporary processing hold.

Do not claim that a deposit was sent, rejected, traced, or held unless an authorized tool or supplied information establishes that fact. Do not request or log identity verification merely to provide general guidance or transfer the customer.

## Procedure

1. Establish whether the deposit is missing versus posted but partially unavailable.
2. For a missing deposit, provide or offer the documented next steps as appropriate:
   - confirm the payer initiated the deposit and its sending schedule;
   - confirm account and routing details with the payer;
   - ask the payer for deposit trace information; and
   - if support follow-up is appropriate, collect the payer name, expected amount, and expected date.
3. Respect an explicit request for a human. Do not continue repetitive troubleshooting after the customer declines it.
4. Choose a transfer reason by the highest applicable policy tier. Specific operational reasons override knowledge-gap reasons, which override customer-disposition reasons. In particular, when the customer is generally frustrated about a missing deposit and asks for a human, use `customer_frustrated_demands_human` unless a higher-tier reason applies.
5. Before calling `transfer_to_human_agents`, optionally run `scripts/build_transfer_plan.py` with facts from the live conversation. Call the bank transfer tool using its returned `reason` and `summary`. The script only recommends a tool call; the executor must make the actual transfer tool call.
6. Give a brief, honest handoff acknowledgement. Do not promise that the human can locate funds or resolve the deposit.

## Transfer-reason decision rules

Set only facts actually supported by the conversation. The helper applies these precedence rules:

- **Tier 1:** fraud/security concern; account closure; deceased holder; legal/regulatory matter; ownership dispute; complex billing dispute; abusive behavior; third-party inquiry; technical system error; persistent demand after an unavailable-offer refusal.
- **Tier 2:** unconfirmed external communication; unsuccessful KB search followed by a transfer request; specialized department; accessibility/special needs.
- **Tier 3:** general frustration plus demand for a human; supervisor/service complaint; no-reason human preference; human follow-up after completion.
- **Tier 4:** `other`, only if none applies; explain why in the summary.

For a direct-deposit customer who says they need their money, expresses urgency or frustration, and explicitly asks to be transferred, mark `frustrated_human_request: true`. Do not classify urgency alone as fraud, a system error, or a specialized-department need.

## Helper interface

Run:

```text
python3 scripts/build_transfer_plan.py
```

The script reads one JSON object from stdin:

```json
{
  "issue_summary": "objective description of the customer's issue",
  "attempted_steps": ["steps already offered or completed"],
  "facts": {
    "fraud_or_security_concern": false,
    "account_closure_request": false,
    "deceased_account_holder": false,
    "legal_or_regulatory_matter": false,
    "account_ownership_dispute": false,
    "complex_billing_dispute": false,
    "abusive_customer_behavior": false,
    "third_party_inquiry": false,
    "technical_system_error": false,
    "persistent_unavailable_offer_demand": false,
    "unconfirmed_external_communication": false,
    "kb_search_unsuccessful_then_transfer": false,
    "specialized_department_required": false,
    "accessibility_or_special_needs": false,
    "frustrated_human_request": false,
    "supervisor_service_complaint": false,
    "human_request_no_specific_reason": false,
    "completed_request_human_followup": false
  }
}
```

It emits JSON containing `transfer`, `reason`, and `summary`. If no transfer fact is present, it returns `transfer: false`; continue the supported customer-service flow rather than calling the transfer tool. `issue_summary` must be factual and should avoid sensitive data not needed for the handoff. Supply a nonempty summary whenever transferring.

## Validation

Before transfer, confirm that the selected reason is one of the transfer tool's enum values, the summary states the customer issue and any attempted/offered step, and no unsupported diagnosis or promise has been added. The helper rejects missing or non-string issue summaries and unknown fact keys.
