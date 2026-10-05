---
name: credit-card-account-closure
version: 1.1.0
description: Safely process an authenticated customer's request to close one specified credit-card account. Use when internal card-account, dispute, replacement-order, retention, and closure tools are available.
---

# Credit Card Account Closure

Use this Skill for a request to close a specific credit-card account. Do not treat a request concerning one card as authority to alter, downgrade, waive fees on, or close another card.

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For closure, record and enforce the applicable prerequisites:

- **Identity:** complete standard identity verification and its audit record before account action.
- **Authority and ownership:** the verified user's ID must equal the selected account's `user_id`.
- **Product and balance eligibility:** verify the account is eligible, has a $0.00 balance, has no pending activity, and has no closure blockers.
- **Fees:** disclose the annual-fee refund rule, but never promise a refund without the fee-posting date and a confirmed determination.
- **Confirmation:** obtain unambiguous authority to close the exact card after retention handling. A customer response such as “continue closing” may be used only when it is clearly tied to the named target card; otherwise ask a direct final question naming the card.
- **Non-applicable controls:** recipient, transfer, payment, and cutoff controls do not apply to a pure closure. If the customer also requests a payment, transfer, redemption, or another product change, use that action's separate workflow and confirmation.

## Runtime inputs and tools

At runtime obtain the verified `user_id`, selected `credit_card_account_id`, card type, current account information, current date/time, transaction status, dispute results, replacement-order results, closure-reason history, the customer's reason, and their final decision.

Before first use of a specialized tool, unlock it with `unlock_discoverable_agent_tool`; then invoke it with `call_discoverable_agent_tool`. A successful unlock is not a successful check: inspect the associated tool result.

| Purpose | Specialized tool | Exact arguments |
|---|---|---|
| Dispute review | `get_user_dispute_history_7291` | `user_id` |
| Replacement review | `get_pending_replacement_orders_5765` | `credit_card_account_id` |
| Prior closure-reason review | `get_closure_reason_history_8293` | `credit_card_account_id` |
| Reason logging | `log_credit_card_closure_reason_4521` | `credit_card_account_id`, `user_id`, `closure_reason` |
| Qualified annual-fee waiver | `apply_credit_card_account_flag_6147` | `credit_card_account_id`, `user_id`, `flag_type`, `expiration_date`, `reason` |
| Closure | `close_credit_card_account_7834` | `credit_card_account_id`, `user_id` |
| Qualified downgrade | `downgrade_credit_card_3847` | `credit_card_account_id`, `user_id`, `target_card_type` |

Pass no extra fields to `log_credit_card_closure_reason_4521`; it accepts only its three listed arguments.

## Procedure

### 1. Verify the customer and select exactly one account

1. Locate the customer using supplied identifying information. If lookup produces multiple customer records, stop and obtain enough information to distinguish the customer.
2. Retrieve the customer's credit-card accounts. Identify the requested card by account-level information, not merely a broad product category. If more than one account could match, ask the customer to identify the intended account.
3. Verify ownership: the selected account's `user_id` must match the authenticated user.
4. Ask the customer to independently provide at least two of date of birth, email address, phone number, and street address. Do not reveal profile values as prompts and do not count a name as one of the two fields.
5. When two values match, obtain the current timestamp with `get_current_time` and create the required `log_verification` audit record with the complete profile fields, user ID, name, and timestamp. If verification fails or is incomplete, do not inspect further account information or take action.
6. Confirm the target in clear language, for example: “You are asking to close your [card type] ending/identified as [safe account reference], correct?” Keep that confirmation associated with this exact account.

### 2. Obtain current closure evidence

Retrieve current account data and confirm its owner, opening date, current balance, and rewards balance. Review available transaction information for the target card. A displayed $0.00 balance does not pass if any transaction is pending, unsettled, or cannot be confidently associated with the target account.

### 3. Determine eligibility before retention

Do not make a retention offer or close the account until every requirement passes. Check in this order:

1. **Disputes:** call `get_user_dispute_history_7291` for the verified user. The target account cannot have an active, pending, open, under-review, unknown, or ambiguously associated dispute. Clearly resolved/closed disputes do not block closure.
2. **Replacement orders:** call `get_pending_replacement_orders_5765` for the target account. An empty orders collection passes. If any order is not clearly `delivered` or `cancelled`, including `pending` or `shipped`, closure is blocked.
3. **Age:** calculate account age from the opening date and current date. It must be at least 60 days.
4. **Balance and transactions:** the outstanding balance must be exactly $0.00 and there must be no pending transaction activity.

If a check has malformed, unavailable, stale, or ambiguous evidence, it does not pass. Explain the blocker and do not offer retention or call the closure tool. For a replacement-order tool failure or ambiguous response, retry only where permitted or escalate through the approved support path.

The packaged evaluator can consistently assess collected evidence; it does not replace verification or any banking tool call:

```sh
python3 scripts/assess_closure_eligibility.py <<'JSON'
{
  "as_of_date": "YYYY-MM-DD",
  "identity_verified": true,
  "closure_authority_confirmed": true,
  "explicit_closure_confirmation": true,
  "verified_user_id": "verified user identifier",
  "account": {
    "account_id": "target account identifier",
    "user_id": "verified user identifier",
    "date_of_account_open": "YYYY-MM-DD",
    "current_balance": "$0.00"
  },
  "pending_transactions_confirmed_absent": true,
  "disputes": [],
  "replacement_orders": []
}
JSON
```

Proceed only when output `eligible` is `true` and `blockers` is empty. The helper's full input/output contract is below.

### 4. Review history, record the reason, and handle retention

Perform these steps only after eligibility passes.

1. Call `get_closure_reason_history_8293` for the selected account. Determine whether a closure-reason record exists within the past year. If it does, skip retention offers and proceed to final closure confirmation. If history cannot be obtained or dates cannot be assessed, stop until resolved.
2. If there is no prior-year record, obtain the customer's reason and map it to exactly one supported reason:
   `annual_fee`, `not_using_card`, `found_better_card`, `unhappy_with_rewards`, `simplifying_finances`, `negative_experience`, or `other`.
3. Call `log_credit_card_closure_reason_4521` using the selected account ID, verified user ID, and that reason only. A customer stating that another issuer's card better meets their needs maps to `found_better_card`.
4. Address the concern without pressure. For a better-card reason, ask which features matter and offer help applying for an internal alternative only when its comparable benefits are actually known. Do not claim that an unknown product is comparable.
5. If no prior-year history exists and the customer still wishes to close, make exactly one retention offer appropriate to the documented card tier:
   - entry tier: 500 points or a $5 statement credit;
   - mid tier: 2,000 points or a $20 statement credit;
   - premium and above: 5,000 points or a $50 statement credit.

Use a verified tier classification; do not infer it solely from an unclassified product name. A clearly documented offer and the customer's response in the interaction record count as evidence. If the customer declines or says they prefer to continue closure, do not apply a retention benefit.

For annual-fee concerns, a customer of at least two years may be offered a one-year waiver; if accepted, use `apply_credit_card_account_flag_6147` with `flag_type` `annual_fee_waived`, a date one year from today in `MM/DD/YYYY`, and reason `loyalty_benefit`. If they have been a customer less than two years, offer a permanent same-category no-annual-fee downgrade instead. Do not infer tenure from unclear records.

If a verified customer selects a downgrade, explain that account history, account number, and credit line are preserved; rewards transfer at the same value; benefits change; and the replacement card arrives in several business days. Use `downgrade_credit_card_3847` with only the same-category target: `Bronze Rewards Card` for personal accounts or `Business Bronze Rewards Card` for business accounts. A downgrade is an alternative to closure, not permission to close.

### 5. Confirm, recheck replacements, and close

1. Obtain final, explicit authority after the retention decision. Name the card in the question: “Do you authorize me to close your [exact card type] account now?” Record the affirmative response. Do not rely on authorization for a different account or a vague answer where multiple cards exist.
2. Immediately before the irreversible closure call, call `get_pending_replacement_orders_5765` again for the target account. This final check is required even if it passed earlier. Do not take substantive account action between this successful final replacement check and closure, apart from necessary tool unlocking.
3. If a balance change, pending transaction, active dispute, new replacement order, or any other blocker is known, stop and explain the unmet prerequisite.
4. Call `close_credit_card_account_7834` exactly as follows:

```json
{"credit_card_account_id":"<target account id>","user_id":"<verified user id>"}
```

5. State that the account closed only after a successful, unambiguous closure-tool result. If the call fails or is ambiguous, accurately report that it was not confirmed closed and use the approved escalation path.

### 6. Post-closure communication

After successful closure, tell the customer that:

- a confirmation email and final statement will arrive within several business days;
- unredeemed rewards can be redeemed for 45 days after the closure request and are permanently forfeited after that;
- a full annual-fee refund may apply only when closure is within 37 days of the annual-fee posting; and
- closure can reduce available credit and affect utilization and credit score.

For a Silver Zoom Card, database rewards labeled as points are cash back worth $0.01 per point when redeemed as a statement credit or checking-account credit. State a cash-back amount only from the current rewards balance. Do not redeem rewards without a separate request, required verification, and the applicable rewards workflow.

## Separate requests and handoffs

Keep a newly raised request about another account separate from the closure workflow. It needs its own verification, account selection, eligibility review, and explicit authorization. If the customer requests specialist review of options (such as annual-fee alternatives) rather than closure, do not close that second account. When a specialist handoff is required, call `transfer_to_human_agents` with reason `specialized_department_required` and a factual summary naming the account, customer request, and completed steps.

## Eligibility helper contract

`scripts/assess_closure_eligibility.py` reads one JSON object from standard input and writes one JSON object to standard output. It makes no tool calls and changes no account state.

Required top-level fields are `as_of_date` (`YYYY-MM-DD`), `identity_verified` (boolean), `closure_authority_confirmed` (boolean), `explicit_closure_confirmation` (boolean), `verified_user_id` (nonempty string), `account`, `pending_transactions_confirmed_absent` (boolean), `disputes` (array), and `replacement_orders` (array). `account` requires nonempty `account_id` and `user_id`, `date_of_account_open` (`YYYY-MM-DD`), and `current_balance` (number or currency string). Each dispute requires `status` and boolean `belongs_to_target_account`; each replacement order requires `status`.

Optional `final_dispute_statuses` is a list of statuses treated as resolved; it defaults to `closed` and `resolved`. Replacement statuses treated as final are always `delivered` and `cancelled`.

Output fields are `eligible` (boolean), `account_age_days` (integer or null), `blockers` (actionable strings), and `checks` (individual outcomes). Missing or invalid evidence always yields `eligible: false`; it is never treated as approval.

## Failure handling

Never bypass an eligibility blocker, substitute another account, or claim a successful action without its successful tool result. If identity, ownership, target selection, confirmation, or specialized-tool execution cannot be established, do not take the banking action. Escalate only through the applicable approved path. If the customer asks for a human, transfer with an accurate summary and the applicable transfer reason.
