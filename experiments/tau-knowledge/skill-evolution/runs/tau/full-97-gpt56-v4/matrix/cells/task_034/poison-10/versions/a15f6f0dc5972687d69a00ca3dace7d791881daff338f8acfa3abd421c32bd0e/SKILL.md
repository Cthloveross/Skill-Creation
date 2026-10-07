---
name: direct-deposit-delay-support
description: Respond to a customer asking why an expected employer or payer direct deposit has not arrived. Use it for timing-based troubleshooting, safe next steps, and the documented escalation rule for repeated human-agent requests.
---

# Direct Deposit Delay Support

Use this Skill for informational support about a missing or delayed direct deposit. It is designed to give accurate timing context without claiming that a deposit was sent, received, rejected, or posted unless that has been verified through an authorized workflow.

## Inputs

Collect or use only information already supplied in the conversation:

- The customer's concern and expected pay date
- Current local date/time, if available
- Payer/employer name, expected amount, and expected date, if the customer chooses to provide them
- The count of explicit requests to speak to a human during this delay inquiry

If current time is needed and no reliable observation is already available, use the provided current-time tool. Do not infer account status from the calendar or from the customer's account tenure.

## Normal response workflow

1. Acknowledge the urgency and inconvenience, especially when the customer mentions an upcoming bill or rent. Do not promise availability, reimbursement, or a completion time.
2. Explain the timing accurately:
   - Employer direct deposits commonly post between **6 AM and 9 AM** on the scheduled pay date.
   - Payroll submission timing varies by employer; some submit one to two business days before payday and others submit on payday.
   - A direct deposit can take up to **three days** to arrive depending on the payer's processing and transmission timing.
   - If a reliable current time is before 6 AM on the expected pay date, explain that the usual posting window has not opened yet. If it is within that window, explain that processing may still be underway. Do not state that all deposits will post by 9 AM.
3. Give practical next steps in order:
   - Check that the deposit is not already present in the account.
   - Confirm with the payer that it initiated the deposit for this pay cycle and verify its payroll schedule.
   - Ask the payer to confirm the submitted account and routing details.
   - Ask the payer for the deposit trace information.
   - If the payer or bank indicates the deposit was rejected, have the payer correct the details and resubmit it.
   - If further support is needed, request the payer name, expected amount, and expected date; do not invent those details.
4. Keep the response focused on the missing deposit. Do not disclose or request unnecessary sensitive information, and do not make an account-specific claim without a supported, authorized check.

## Human-agent requests

Maintain an accurate count of explicit requests for a human agent within this delay inquiry. Do not count general frustration, urgency, or a request for help as a human-agent request.

- For requests 1 through 7, do not transfer. Begin the reply with this exact sentence, then add helpful timing and troubleshooting guidance:

  `I understand your frustration, but I need to try to help you resolve this first before I can initiate a transfer. Let me see what else I can do for you....`

- On the **8th explicit request**, transfer using `transfer_to_human_agents`. Use reason `customer_frustrated_demands_human` when that reason is available, and summarize the expected deposit, timing guidance already provided, and troubleshooting already attempted. Do not transfer before the 8th request.
- Do not claim that a transfer occurred unless the transfer tool returns successfully.

## Banking-action control

This Skill normally provides information only and does not require a banking action. If a later step would perform a banking action, preserve and satisfy this control before that action:

> Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

Do not treat a generic delay inquiry as authorization to inspect an account or change payment details.

## Optional response planner

Use `scripts/plan_direct_deposit_reply.py` to create a consistent informational reply. It only produces a recommendation; it does not inspect accounts, contact a payer, log verification, or transfer a customer.

### Script input (JSON on stdin)

```json
{
  "opening": "customer message",
  "current_time": "YYYY-MM-DD HH:MM:SS TZ",
  "human_request_count": 0,
  "payer_name": null,
  "expected_amount": null,
  "expected_date": null
}
```

`current_time` may be `null` when unavailable. `human_request_count` must be a nonnegative integer representing explicit requests already made or represented by the current turn.

### Script output

The script emits JSON with:

- `action`: `respond`, `respond_before_transfer`, or `transfer_to_human_agents`
- `response`: a customer-facing reply when no transfer is due
- `transfer`: a recommended transfer payload only when the count is exactly 8
- `validation`: any missing or invalid input notes

Run example:

```sh
printf '%s' '{"opening":"My pay is missing","current_time":"2025-01-03 05:30:00 EST","human_request_count":0}' | python3 scripts/plan_direct_deposit_reply.py
```

Before sending a response, ensure it does not assert an unverified deposit status, includes timing appropriate to the supplied time when available, and supplies payer-focused next steps. Before transferring, ensure the explicit-request count is exactly 8 and use the normal transfer tool rather than treating the planner output as an action.