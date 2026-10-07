---
name: atm-fee-review-and-correction-triage
description: Review suspected ATM-fee or ATM-rebate discrepancies for Bluest and Light Green checking accounts, calculate only policy-based preliminary comparisons from customer-provided transaction data, and safely triage any possible correction when account and transaction tools are unavailable.
---

# ATM Fee Review and Correction Triage

Use this Skill when a customer questions ATM fees, ATM fee rebates, or a possible fee correction on a Bluest or Light Green checking account.

## Safety and banking prerequisites

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

A fee-refund or missing-rebate credit is a banking action. Do **not** apply or recommend applying a credit merely because a customer believes a fee is high.

For any possible credit, establish all of the following first:

1. Identity verification: have the customer confirm at least two of date of birth, email, phone number, and address, without reading the values to them. Compare against the retrieved customer record and call `log_verification` only after two fields are confirmed.
2. Authority and ownership: verify that the customer owns the particular account and is authorized to discuss it.
3. Account eligibility: verify the account is an active checking account and identify the actual account product.
4. Transaction evidence: review the relevant posted and pending transaction history, including ATM withdrawals, bank ATM fees, third-party operator fees, rebates, and prior refunds.
5. Policy facts: determine the applicable statement cycle, fee location/type, individual withdrawal amount, and whether a fee is the bank's fee or a separate ATM-operator fee.
6. Correction basis: calculate the exact net discrepancy, confirm no equivalent rebate or refund was already posted, and ensure any requested credit is allowed by policy.

Never disclose account details, balances, dates of birth, addresses, phone numbers, or transaction data to an unverified person. A name alone is not an identity factor. A name plus an email used to locate a record is normally only one confirmed identity factor unless the customer separately confirms another permitted field.

## Tool boundaries

Use only tools actually supplied in the current runtime. Do not attempt to unlock, call, infer results from, or substitute for a documented account-listing, account-transaction, or checking-credit tool when it is not supplied.

The documented account-information and transaction-history tools may not be available in a given runtime. If either account ownership/account type or transaction history cannot be retrieved with the supplied tools, do not guess account IDs, products, balances, fees, or rebates. Ask for a customer-provided, redacted transaction transcription or statement information if the customer can provide it. Needed items are:

- account product for each account;
- statement-cycle dates or confirmation that the entries are all in one statement cycle;
- each withdrawal date, amount, and whether it was foreign;
- each associated Rho-Bank fee and any separate operator surcharge; and
- all ATM-related rebate, refund, or credit entries.

If the customer cannot provide the data, or the response is unavailable/out of scope, explain that a definitive review and any credit cannot be completed in the available system. Direct them to their mobile app, online banking/help center, or customer service for their transaction history. If they ask for the issue to be handled or escalated, use `transfer_to_human_agents` with `reason: "complex_billing_dispute"` and a concise factual summary of the missing access and requested review. Do not transfer merely to avoid explaining the limitation.

## Product rules for preliminary review

Apply only the rule that matches the confirmed product and facts.

### Bluest

- Bluest provides rebates for third-party ATM fees up to **$50 per monthly statement cycle**.
- Eligible rebates stop once aggregate eligible ATM fees reach $50 in that statement cycle.
- Third-party operator fees may still be charged, including at foreign ATMs.
- The ongoing balance requirement to keep all Bluest benefits active is a daily balance of **$112,500**. Do not assume benefits were active without account information.

A preliminary potential missing rebate is no more than the lesser of total eligible third-party ATM fees and $50, minus confirmed ATM-rebate credits already posted for the same statement cycle. This is not approval for a credit: eligibility, product status, the cycle, and transaction history must still be verified.

### Light Green

- Maintenance eligibility requires that the customer be the primary account holder and age 13 through 24.
- The account includes four free out-of-network ATM withdrawals per month; afterward, the Rho-Bank out-of-network ATM withdrawal fee is $1.50 per withdrawal.
- For a foreign ATM withdrawal, the Rho-Bank fee is based on that individual withdrawal: $2.00 up to and including $100; $3.50 above $100 through and including $300; and $5.00 above $300.
- A foreign-ATM Rho-Bank fee is separate from any ATM-operator surcharge. Do not treat an operator surcharge as a Rho-Bank mischarge without evidence of a separate applicable reimbursement policy.

Do not combine the domestic free-withdrawal rule with the foreign tiered-fee rule unless authoritative transaction/account information explicitly establishes that both fees were charged and both rules apply.

## Optional deterministic calculation helper

When complete customer-provided entries are available, run:

```text
scripts/assess_atm_fees.py
```

The script reads one JSON object from standard input and emits one JSON object on standard output. It performs a preliminary arithmetic comparison only; its output never authorizes a credit or a bank action.

### Input schema

```json
{
  "product": "bluest" | "light_green",
  "statement_cycle": "customer-supplied cycle label",
  "benefits_active": true,
  "entries": [
    {
      "sequence": 1,
      "withdrawal_amount": "125.00",
      "is_foreign": false,
      "rho_bank_fee": "0.00",
      "third_party_fee": "3.00",
      "rebate_credit": "0.00"
    }
  ]
}
```

`entries` must be in a single statement cycle and have unique chronological `sequence` values. `withdrawal_amount` is required for Light Green foreign entries. For Bluest, `third_party_fee` is the eligible third-party ATM fee and `rebate_credit` is a confirmed posted ATM-rebate amount. Use nonnegative decimal dollar strings. Leave a non-applicable monetary field as `"0.00"`.

### Output interpretation and validation

The output contains `status`, `assumptions`, per-entry expected fee comparisons when applicable, and totals rounded to two decimal places. A `needs_more_information` status means do not draw a conclusion. A `preliminary_discrepancy` means the provided facts warrant transaction-history verification, not an automatic correction. Validate that the product, cycle, fee attribution, chronological entry list, and all amounts match the customer-provided statement before relying on the result.

## End-to-end conversation procedure

1. Acknowledge the concern and identify the two claimed products, but do not state that a charge is wrong.
2. Locate a customer record only with a supplied lookup tool and customer-provided identifier. Obtain two valid identity confirmations and log verification if the runtime supports it.
3. Verify ownership, account type/product, benefit eligibility, and transactions using only supplied tools. If those tools are missing, explain the limitation rather than fabricating a review.
4. Obtain the required redacted statement facts. For Light Green, specifically ask whether a withdrawal was foreign and whether the charge was a bank fee or operator surcharge.
5. Use the helper for complete data, then reconcile its preliminary arithmetic against authoritative transaction history when available.
6. Only after all prerequisites are satisfied, determine whether a fee mischarge or missing rebate exists. If a checking-account credit tool is supplied and policy authorizes it, follow its one-credit/cooldown constraints, use the exact positive amount, and use the appropriate documented credit type (`fee_refund` for a mischarged fee; `rebate_credit` for a missing rebate). Combine permitted corrections only as the tool policy requires.
7. If a credit cannot be verified or the necessary tool is unavailable, do not perform a banking action. Give the customer the review path or, on request, transfer the billing dispute.
8. State the outcome precisely: what could be reviewed, what could not be verified, any next step, and that no credit was applied unless a successful credit tool result confirms otherwise.
