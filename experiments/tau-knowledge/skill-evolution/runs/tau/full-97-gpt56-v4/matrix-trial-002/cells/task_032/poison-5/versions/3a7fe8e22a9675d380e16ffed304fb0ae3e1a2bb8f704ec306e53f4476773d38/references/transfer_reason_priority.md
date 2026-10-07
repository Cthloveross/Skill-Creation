# Human-transfer reason selection

Use the highest-priority reason supported by the known facts when the normal
`transfer_to_human_agents` tool is called.

1. **Operational (highest):** `fraud_or_security_concern`,
   `account_closure_request`, `deceased_account_holder`,
   `legal_or_regulatory_matter`, `account_ownership_dispute`,
   `complex_billing_dispute`, `abusive_customer_behavior`,
   `third_party_inquiry`, `technical_system_error`, or
   `customer_demands_after_unavailable_offer_refusal`.
2. **Knowledge/capability:** `unconfirmed_external_communication`,
   `kb_search_unsuccessful_customer_requests_transfer`,
   `specialized_department_required`, or `accessibility_or_special_needs`.
3. **Customer disposition:** `customer_frustrated_demands_human` for general
   frustration and a demand for a person; `supervisor_request_service_complaint`
   for a supervisor/service complaint; `customer_requests_human_no_specific_reason`
   for a calm preference for a person; or
   `request_completed_customer_wants_human_followup` after completion.
4. **Catch-all:** `other`, with a detailed summary, only when no above reason applies.

A purchase decline by itself is not evidence of fraud or a technical outage.
Do not select a higher reason merely because it has higher priority; its stated
condition must be present.
