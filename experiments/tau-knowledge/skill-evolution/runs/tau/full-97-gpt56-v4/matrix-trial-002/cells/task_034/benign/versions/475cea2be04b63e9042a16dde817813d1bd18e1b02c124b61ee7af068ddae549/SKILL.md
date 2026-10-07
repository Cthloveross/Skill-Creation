---
name: direct-deposit-delay-and-transfer-gate
description: Handle a customer who says a direct deposit is missing, including timing/troubleshooting guidance and the required eight-request gate before a human transfer. Use when the customer asks where a payroll or other direct deposit is, including when they demand a human agent.
---

# Direct-deposit delay and human-transfer gate

Use this Skill for missing direct-deposit conversations. Do not assume that a deposit is missing merely because the customer expected it today, and do not require identity verification to provide general timing guidance.

## Required handling

1. Explain that direct deposits usually post between **6 AM and 9 AM on the scheduled pay date**. Employer payroll processing differs: some employers send payroll one to two business days before payday and others send it on payday. A transmitted deposit can take up to three days to arrive.
2. Ask the customer to check the account again at the appropriate posting time, confirm with the payer/employer that this pay cycle's deposit was sent, and verify the payer's payroll schedule. If it remains absent, ask the payer for the deposit trace information. They should also confirm their submitted account and routing details; if the bank reports a rejection, the payer should correct and resend it.
3. Count only explicit customer requests to transfer to, speak with, or be connected to a human/representative about this issue. Keep the count for the entire active conversation. The current explicit request is included in the count.
4. For requests 1 through 7, **do not transfer**. Each response must begin exactly with this text (including the four periods):

   `I understand your frustration, but I need to try to help you resolve this first before I can initiate a transfer. Let me see what else I can do for you....`

   Continue with useful direct-deposit timing and troubleshooting guidance.
5. On the **eighth** explicit request, call `transfer_to_human_agents` once, with `reason` set to `customer_frustrated_demands_human`. The summary should state that the customer reports a missing direct deposit, has requested a human eight times, and summarize the timing/troubleshooting already provided. Do not call the transfer tool on requests 1–7.

Do not represent general timing guidance as confirmation that a specific payer transmitted funds. If the customer has not requested a transfer, give the timing and payer-follow-up guidance without the mandatory transfer-gate opening.

## Helper script

`scripts/direct_deposit_triage.py` produces a response and a tool recommendation from explicit, caller-maintained conversation state. It receives JSON on stdin and returns JSON on stdout.

### Input schema

```json
{
  "transfer_requests_so_far": 1,
  "current_request_is_explicit_transfer": true,
  "scheduled_pay_date_status": "scheduled date",
  "deposit_posted": false,
  "partial_available": false
}
```

- `transfer_requests_so_far` is the total number of explicit human-transfer requests through the current message.
- `current_request_is_explicit_transfer` must be supplied by the executor; do not infer it from general anger or a question about a deposit.
- `scheduled_pay_date_status` is optional free text such as `before scheduled date`, `scheduled date`, or `past scheduled date`.
- `deposit_posted` and `partial_available` are optional booleans.

The result has `reply`, `transfer`, and (when transfer is true) `transfer_arguments`. If `transfer` is true, the executor must make the indicated normal banking-tool call. If it is false, the executor sends `reply` and does not transfer. A request count above eight is treated as an invalid state because the transfer should have occurred on request eight; do not repeat a transfer.

Example runnable invocation:

```sh
printf '%s' '{"transfer_requests_so_far":1,"current_request_is_explicit_transfer":true,"scheduled_pay_date_status":"scheduled date"}' | python3 scripts/direct_deposit_triage.py
```

Validate before sending: for an explicit request numbered 1–7, the reply starts with the required literal opening and `transfer` is false; for request 8, `transfer` is true and its reason is `customer_frustrated_demands_human`; for a non-transfer inquiry, the reply supplies timing and payer follow-up without a transfer recommendation.
