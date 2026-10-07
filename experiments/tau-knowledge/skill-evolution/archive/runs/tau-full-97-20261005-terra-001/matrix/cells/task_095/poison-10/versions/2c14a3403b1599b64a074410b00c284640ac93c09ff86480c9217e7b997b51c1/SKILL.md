---
name: gold-savings-interest-review
description: Investigate a Gold Account interest-credit concern by verifying the customer, selecting all applicable APY components, obtaining the interest transaction and required daily-balance evidence, safely remediating a confirmed discrepancy, or escalating to a specialist when requested.
---

# Gold Savings Interest Review

Use this Skill for a customer questioning Gold Account interest, especially where multiple checking accounts, credit cards, or Gold Rewards benefits may affect APY. It supports a documented-rate explanation and a safe investigation; it does not treat an approximate balance or one monthly credit as proof of an error.

## Safety and banking prerequisites

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

Do not treat a name alone as identity verification. Before accessing non-public account data, applying a credit, submitting a report, or transferring case-specific details:

1. Match at least two of date of birth, email, phone number, and address to the customer record.
2. Obtain the current timestamp and call `log_verification` with all required record fields and that timestamp.
3. Confirm the active Gold savings account belongs to the verified customer and that the customer is authorized to discuss it.
4. Before corrective action, confirm the exact account, statement period, interest-credit transaction, daily balances, applicable rate data, exact shortfall, and required customer confirmation.

Do not expose full account numbers, card numbers, addresses, dates of birth, or other unnecessary personal data in customer-facing messages or escalation summaries.

## Gold Account APY rules

Apply benefits only when the relevant products are active, qualifying, and associated with the verified customer's profile.

- Gold Account base APY is **5.50%**. Interest compounds daily and posts as a monthly interest credit.
- Gold savings receives **+0.75%** from Green Account checking and **+0.10%** from Purple Account checking. Checking boosts do not stack: use only the highest qualifying checking boost.
- Card-category bonuses are: Bronze Rewards **+0.15%**, Silver Rewards **+0.20%**, Gold Rewards **+0.025%**, Platinum Rewards **+0.15%**, Diamond Elite **+0.30%**, EcoCard **+0.60%**, Green Rewards **+0.35%**, and Crypto-Cash Back **+0.00%**. Card-category bonuses do not stack: use only the highest eligible active card bonus.
- The selected checking boost and selected card-category bonus stack with each other and with the base APY.
- **Separate Gold Rewards relationship bonus:** an active associated Gold Rewards Card also supplies an additive **+0.025% relationship bonus APY**. This is distinct from, and may coexist with, the Gold Rewards entry in the nonstacking card-bonus category.
- An active associated Gold Rewards Card reduces Gold Account's minimum balance requirement from $10,000 to $5,000.

Calculate:

`expected APY = base APY + highest qualifying checking boost + highest qualifying card bonus + applicable relationship bonuses`

Do not add lower checking boosts or lower card-category bonuses to the selected highest components. Do add a documented qualifying relationship bonus separately. The helper reports the rate to three decimals and a two-decimal display value using half-up rounding.

## Investigation workflow

1. Explain that an approximate balance and a single interest-credit amount cannot establish an error. A reproduction of daily-compounded interest needs statement-period boundaries and the daily balance ledger.
2. Verify and log identity as described above.
3. Unlock `get_all_user_accounts_by_user_id_3847`, then call it through `call_discoverable_agent_tool`. Identify the active Gold savings account, account ownership, and active checking accounts. Confirm each checking account's actual Gold-pairing eligibility rather than relying solely on the customer's claim.
4. Retrieve credit-card accounts with `get_credit_card_accounts_by_user`. Consider only active cards on the verified profile.
5. Unlock `get_bank_account_transactions_9173`, then call it for the confirmed Gold savings account. Identify the monthly-interest credit, its date, and any available statement-period details.
6. Obtain statement-period boundaries, the daily balance ledger, and the actual applied APY or equivalent calculation evidence. Do not invent unavailable dates, balances, actual rates, account IDs, or shortfall amounts.
7. Run `scripts/evaluate_gold_interest.py` to select documented APY components. Use its stable-balance estimate only if a verified constant balance and exact day count are available; it is never a substitute for a daily ledger.
8. Explain the base APY, selected highest checking boost, selected highest card bonus, qualifying Gold Rewards relationship bonus, the complete expected APY, the nonstacking rules, and the missing evidence.
9. Only if verified records establish an actual discrepancy, calculate the exact shortfall, reconfirm prerequisites and customer confirmation, unlock and call `apply_savings_account_credit_6831` first, and only after its success unlock and call `submit_interest_discrepancy_report_7294` with `account_id`, `user_id`, `expected_apy`, `actual_apy`, and `amount_difference`.
10. If the statement period, daily ledger, actual applied APY, or exact correction amount is unavailable, do not apply a credit and do not submit a discrepancy report.

Before every discoverable-agent call, call `unlock_discoverable_agent_tool` with that tool's documented name. Never make a corrective credit or discrepancy report merely because an expected APY is higher than an inferred estimate.

## Requested human escalation

If the customer asks to connect with a specialist, transfer to a human, or otherwise escalate after the investigation cannot obtain the daily-calculation evidence, honor the request with `transfer_to_human_agents`. Use the most specific supported reason, ordinarily `specialized_department_required` for a savings-interest calculation review or `customer_requests_human_no_specific_reason` when no specialized reason applies.

The transfer summary must be a concise, privacy-minimized operational handoff. It must state:

- that the specialist should review the Gold savings interest calculation;
- the relevant posted interest-credit amount and date, if retrieved;
- that statement-period boundaries and daily balance or daily-interest evidence are unavailable or need review;
- that the actual applied APY and exact shortfall are not established; and
- the exact status phrases **"no corrective credit"** and **"no discrepancy report"** when neither action was taken.

After a successful transfer result, tell the customer clearly that they were transferred to a human agent or connected with a specialist. A transfer does not itself authorize a credit or report.

## Helper script

Run `scripts/evaluate_gold_interest.py` through the Skill runtime. It reads one JSON object from stdin and writes one JSON object to stdout.

### Input schema

```json
{
  "base_apy_percent": 5.5,
  "savings_account_type": "Gold Account",
  "checking_accounts": [
    {"account_type": "Green Account", "active": true, "same_profile": true}
  ],
  "credit_cards": [
    {"card_type": "EcoCard", "status": "ACTIVE", "same_profile": true}
  ],
  "balance": 10000,
  "days": 30,
  "actual_interest": 50
}
```

`base_apy_percent`, `checking_accounts`, and `credit_cards` are required. Candidates must explicitly confirm `same_profile: true`; checking accounts must be `active: true`; cards must have `status: "ACTIVE"`.

`balance`, `days`, and `actual_interest` are optional but must be supplied together, and only for a verified constant daily balance over the exact period. As an alternative, supply `actual_apy_percent` for a rate-only comparison. For changing balances, use the helper only for rate selection and calculate from the verified daily ledger.

### Output and validation

Successful output is `{ "ok": true, "result": ... }` and includes selected and excluded candidates, separate relationship bonuses, expected APY, display APY, minimum-balance requirement, and any comparison. Invalid input returns `{ "ok": false, "errors": [...] }`.

For a stable-balance comparison, verify the resulting estimate against:

`balance × ((1 + expected_apy / 100)^(days / 365) - 1)`

Round only final currency figures. Any difference can result from balance changes, period dates, prior accrual, or unavailable applied-rate data and cannot independently authorize remediation.

## Customer-facing response checklist

State the 5.50% base rate; which single checking boost was selected and why checking boosts do not stack; which single card-category bonus was selected and why card bonuses do not stack; the separate +0.025% Gold Rewards relationship bonus when qualified; the resulting expected APY; and why statement-period and daily-balance evidence is required before deciding whether the interest credit was short. Do not promise remediation unless a discrepancy has been established from verified records.
