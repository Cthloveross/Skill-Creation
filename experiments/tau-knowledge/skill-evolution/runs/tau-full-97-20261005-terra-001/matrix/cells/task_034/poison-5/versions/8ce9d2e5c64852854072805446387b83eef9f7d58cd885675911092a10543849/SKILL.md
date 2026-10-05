---
name: direct-deposit-delay-support
description: Handle customer reports that an expected direct deposit has not arrived, including timing and payer-trace troubleshooting and the mandatory eight-request threshold before a human-agent transfer.
---

# Direct Deposit Delay Support

Use this Skill when a customer says an employer or other payer direct deposit is missing, late, or only partly available. It is designed for ordinary incoming direct-deposit timing issues, not for fraud, account closure, or unrelated requests.

## Required handling

1. Acknowledge urgency without promising a deposit time or outcome.
2. Explain that deposits commonly post between **6 AM and 9 AM on the scheduled pay date** once received. Payers may process payroll **1–2 business days early** or on the official pay date, and transmission can take **up to 3 days**.
3. Ask the customer to verify with the payer that this cycle's deposit was sent, the official pay date/transmission time, the expected amount, and the ACH/direct-deposit trace information. They should also confirm the account and routing information the payer used.
4. If an account ID is already available and reviewing transactions is appropriate, the executor may use `get_bank_account_transactions_9173(account_id)` to check for posted or pending activity. Do not claim a deposit is absent, rejected, or pending unless tool results establish that. Do not request unrelated identity data solely for a timing inquiry.
5. If a deposit has posted but less is available than expected, explain that a temporary hold can apply to part of the paycheck while processing completes.

## Human-transfer threshold

Maintain a per-conversation count of **distinct customer requests for a human agent**. Count only an actual customer request or demand to transfer; do not count agent statements, customer frustration alone, or repeated wording within the same customer turn as multiple requests.

- Requests 1 through 7: do **not** transfer. Each response must begin exactly with this required text:

  `I understand your frustration, but I need to try to help you resolve this first before I can initiate a transfer. Let me see what else I can do for you....`

  Immediately follow it with useful direct-deposit timing or payer-verification guidance.
- Request 8: perform `transfer_to_human_agents`. For a generally frustrated customer demanding a person, use `customer_frustrated_demands_human`. Use a higher-priority reason code instead if a documented higher-tier situation independently applies.
- Treat a recorded count above 8 as a counting/data-integrity exception: do not silently reinterpret it as the eighth request. Review the conversation count before taking a transfer action.

A customer who has requested a human only once must receive the required no-transfer response, even if they are upset or have an urgent bill due.

## Transfer summary

When the eighth request is reached, summarize the missing deposit, expected pay date if known, payer-confirmation/trace status, any transaction review actually performed, timing guidance already provided, and that this is the customer's eighth distinct transfer request. Do not invent an amount, payer confirmation, trace number, or transaction result.

## Planner script

Use `scripts/plan_direct_deposit_delay.py` to make the threshold decision consistently. It reads one JSON object from stdin and emits one JSON object to stdout.

### Input schema

```json
{
  "human_request_count": 1,
  "customer_frustrated": true,
  "expected_pay_date": "optional customer-provided date",
  "employer_confirmed_sent": null,
  "trace_number_available": null,
  "deposit_status": "unknown",
  "transaction_review": "not_performed"
}
```

- `human_request_count` is the cumulative number of distinct transfer requests **including the current customer turn**.
- `customer_frustrated` is a boolean determined from the conversation.
- `employer_confirmed_sent` and `trace_number_available` are `true`, `false`, or `null` when unknown.
- `deposit_status` is `missing`, `partial_availability`, `posted`, or `unknown`.
- `transaction_review` is a short factual status such as `not_performed` or `reviewed`; it is included only to build an accurate handoff summary.

### Example call

```bash
python3 scripts/plan_direct_deposit_delay.py <<'JSON'
{"human_request_count":1,"customer_frustrated":true,"expected_pay_date":null,"employer_confirmed_sent":null,"trace_number_available":null,"deposit_status":"unknown","transaction_review":"not_performed"}
JSON
```

Interpret `action: "respond"` by sending `customer_response` verbatim before adding only factual, case-specific information. Interpret `action: "transfer"` by calling `transfer_to_human_agents` with the supplied `transfer` object. `action: "review_count"` requires resolving the count discrepancy rather than executing a transfer.

## Validation

Before sending or transferring, confirm:

- The issue is an expected incoming direct deposit rather than an unsupported issue.
- The request count is cumulative and includes the current turn exactly once.
- Counts below 8 produce no transfer and retain the required response prefix.
- Count 8 produces the transfer action and an applicable reason code.
- Any claimed deposit status or trace detail is supported by the customer or an actual tool result.
