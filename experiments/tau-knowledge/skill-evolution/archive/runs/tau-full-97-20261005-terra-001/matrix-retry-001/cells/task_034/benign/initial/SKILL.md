---
name: direct-deposit-delay-support
version: 1.0.0
description: Handle customers whose expected direct deposit has not arrived, including timing guidance, safe account-specific investigation, and the eight-request human-transfer gate.
---

# Direct deposit delay support

Use this Skill for a customer asking where an expected direct deposit/paycheck is, including requests to transfer to a human during that conversation.

## Required operating rules

1. Treat the issue first as a direct-deposit timing or payer-transmission question. Direct deposits typically post between **6 AM and 9 AM on the scheduled pay date**. Employers may process payroll **one to two business days before** the official pay date or on the pay date itself. A deposit can take **up to three days** depending on when the payer processes and transmits it.
2. Ask the customer to verify the expected pay date, payer/employer or payroll provider, expected amount, whether the payer confirms it was sent, and any deposit trace information. Ask them to confirm the account and routing information held by the payer when appropriate.
3. Do not claim that a deposit was sent, received, rejected, pending, or held unless supported by an available account record or payer information.
4. If the customer says a deposit has posted but available funds are lower than expected, explain that a temporary hold may apply to part of the paycheck until processing completes.
5. A request for a human in a direct-deposit-delay conversation is transfer-eligible only when the customer has made their **eighth** request. Count only explicit customer requests to speak with, be transferred to, or be connected with a human/agent/representative. Do not count agent statements, questions, or vague expressions of dissatisfaction as requests.
6. For every request number 1 through 7, do not transfer. Begin the response with this exact text, including its punctuation, and then provide useful assistance:

   `I understand your frustration, but I need to try to help you resolve this first before I can initiate a transfer. Let me see what else I can do for you....`

7. On request number 8, use `transfer_to_human_agents`. Select the highest applicable reason code. For a generally frustrated customer demanding a human, use `customer_frustrated_demands_human`; if they are simply requesting a person without frustration, use `customer_requests_human_no_specific_reason`. A higher-tier reason always overrides these disposition reasons.
8. Do not attempt a transfer at a count greater than eight as a substitute for the required eighth-request action. If the eighth request was not actioned because of a process interruption, preserve the count and follow the active operational escalation process rather than silently resetting or re-counting it.

## Workflow

### 1. Establish what is known

Read the conversation and maintain a per-conversation count of explicit human-transfer requests. The count must include the current customer message when it explicitly asks for a human. Do not infer requests from urgency alone.

If the customer has not supplied account-identifying information, request the email address or full name on the account only as needed to locate the correct profile. Do not expose account-specific details before identity verification.

### 2. Provide practical delay guidance

Acknowledge the urgency without promising availability. Explain the relevant timing window or up-to-three-day payer-processing possibility. Ask the payer to confirm that it initiated the payment for this pay cycle and to provide a deposit trace. If the payer says the bank rejected it, advise the customer to correct account/routing details with the payer and request resubmission.

When the current time is before the typical scheduled-pay-date posting window, tell the customer to check again during or after that window. When it is already later, do not assert an error; continue with payer confirmation, trace information, and account review when authorized.

### 3. Investigate only when authorized and supported

For account-specific review, complete the runtime's required identity verification. When the runtime provides the applicable customer and account identifiers and the transaction-history tool is available, use `get_bank_account_transactions_9173(account_id)` to review the account history. Inspect direct-deposit records and their status; transaction records are reverse chronological. If the account has no matching deposit, say only that no matching record was found in the reviewed history, not that the payer failed to send it.

After confirming two of the available identity fields (date of birth, email, phone number, address), call `log_verification` with the verified profile fields and the runtime timestamp before continuing account-specific handling. Never invent identity fields, an account ID, payer confirmation, trace number, or a transaction result.

### 4. Apply the transfer gate

Use `scripts/direct_deposit_plan.py` to validate the known request count and produce a deterministic next-action plan. The script does not call banking tools or transfer a customer. The executor must carry out its returned action using the normal runtime tools.

* Before the eighth request, respond using the required exact opening and helpful next steps. Continue troubleshooting instead of transferring.
* At the eighth request, create an accurate summary of the expected deposit, timing, payer confirmation/trace status, account review if any, and assistance already attempted. Then call `transfer_to_human_agents` with the plan's reason unless a documented higher-priority reason applies.
* A transfer tool call is the actual transfer; a script recommendation or prose response is not.

## Planner interface

Run `scripts/direct_deposit_plan.py` with one JSON object on stdin. It emits one JSON object on stdout.

Input schema:

- `transfer_request_count` (integer, required): total explicit customer requests for a human in this direct-deposit conversation, including the current message.
- `customer_frustrated` (boolean, required): whether the customer currently expresses general frustration/urgency while requesting a human.
- `higher_priority_reason` (string or null, optional): a valid Tier 1 or Tier 2 transfer reason already established by the conversation. Do not supply a reason merely because the customer is unhappy.
- `payer_confirmed_sent` (boolean or null, optional)
- `trace_information_available` (boolean or null, optional)
- `account_review_completed` (boolean, optional; default `false`)
- `current_time` (string or null, optional): current runtime timestamp, retained in the plan for the response author.

Output schema:

- `action`: `continue_support`, `transfer_now`, or `manual_process_review`.
- `must_not_transfer`: boolean.
- `transfer_reason`: a reason code or null.
- `required_opening`: exact required opening for a denied pre-eighth transfer request, or null.
- `response_points`: ordered factual points to incorporate in the customer response.
- `summary_checklist`: facts to include in a transfer summary when a transfer is authorized.

Validate that the count is a non-negative integer, booleans are actual JSON booleans, and a supplied higher-priority reason is an allowed Tier 1/Tier 2 reason. Treat script validation errors as missing/invalid workflow data: correct the structured state from the conversation rather than guessing.

A runnable invocation is `python3 scripts/direct_deposit_plan.py`, with the JSON object above provided on standard input. The expected output is a single valid JSON object with no diagnostic text on standard output.
