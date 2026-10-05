---
name: business-checking-referral-eligibility-and-selection
description: Safely handle requests to refer a business to a Rho-Bank business checking product, including eligibility gating, referral-limit checks, and account selection when the customer wants the largest referrer bonus. Use for informational referral guidance; it does not submit or create a referral.
---

# Business Checking Referral Eligibility and Selection

## Scope and safety boundary

Use this Skill when a customer wants referral information, wants to refer a business, or asks which business checking referral produces the best referrer reward. It is decision support only. Do **not** create a referral, alter an account, disclose protected account data, or imply that qualification or payment is guaranteed.

If the customer says `STOP`, `###STOP###`, asks not to continue, or otherwise withdraws from the process:

1. Stop immediately.
2. Do not ask another eligibility question, query customer records, calculate recommendations, or take any banking action.
3. Acknowledge that the referral review is paused and say they may resume if they choose.

The bundled evaluator returns `stopped` for this state.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Required eligibility gate

Do not give account-specific referral terms or recommend an account based on a referral bonus until the referrer is eligible to submit referrals. Collect or verify the following, without requesting SSNs or other full sensitive identifiers in chat:

1. **Identity and authority:** Authenticate the referrer before accessing their referral history or other protected account data. A name lookup alone is not authentication. Where the runtime supports it, have the customer confirm two profile fields, then log the verification with the current timestamp before using account-specific tools.
2. **Referrer tenure:** Verify the date of the earliest Rho-Bank checking account and calculate exact tenure. Account type does not change the tenure calculation.
3. **Rolling cap:** Retrieve the referrer's successful referral-bonus timestamps. At most two bonuses may fall in the immediately preceding rolling nine-day period, across all checking products.
4. **Annual cap:** Determine how many referral bonuses have already been paid in the current calendar year for the proposed product and compare against that product's annual cap.
5. **Referred business restrictions:** Confirm all of these separately:
   - the referred person/business is a new Rho-Bank customer and has had no checking, savings, or closed account in the past 12 months;
   - the referrer and referred person have different registered addresses;
   - for a business referral, the prospective business has a different primary owner/primary authorized signer SSN from every existing Rho-Bank business account;
   - the prospective owner is an eligible adult;
   - the qualifying deposit will be new money, not a transfer from another Rho-Bank account;
   - no conflicting new-account promotion or sign-up bonus will be used, and only one referral code will be applied.
6. **Qualification and payment conditions:** Confirm the prospective business can open the recommended product and meet the product-specific deposit amount and deadline. Explain that the qualifying deposit must remain for at least 30 days after the qualifying period, both accounts must remain in good standing, and a bonus can be reversed if the referred account closes within 90 days.

A customer statement about an approximate account-opening date is useful for screening, but is not a substitute for an authenticated account record when a referral is to be submitted or personalized account history is to be used.

## Conversation procedure

1. Check for a stop/withdrawal instruction first. If present, pause without further work.
2. State briefly that eligibility must be confirmed before referral recommendations can be given.
3. Ask only for missing gate items. Group the two unresolved new-customer/primary-owner questions together so the customer can answer clearly. Do not infer that a former partner, separate apartment, or separate company necessarily establishes new-customer status or distinct primary ownership.
4. After identity/authority verification, use available read-only customer/referral tools to verify the referral history. Record only the facts needed for the decision; never echo profile data, full SSNs, or account numbers.
5. Convert the verified facts to the JSON schema below and run `scripts/evaluate_referral.py`.
6. Interpret the result:
   - `stopped`: acknowledge the pause only.
   - `needs_verification`: ask only the listed missing confirmations or obtain the indicated authenticated record.
   - `blocked_ineligible`: explain the failed condition plainly; do not suggest bypasses.
   - `no_matching_program`: explain that no currently supported program matches the verified tenure/deposit constraints.
   - `eligible_options`: present the selected account and material conditions. Frame it as conditional on the facts remaining true.
7. If the customer wants to proceed with a referral after receiving information, re-check all mandatory banking controls immediately before any actual referral action. This Skill has no referral-submission capability; use only normal authorized banking tools if such a capability is available.

## Selecting an account

The evaluator uses the program terms in `references/referral_terms.json`.

- For an explicit goal of **maximizing the referrer's bonus**, select the eligible program with the greatest referrer bonus. Do not allow a promotional-priority account to defeat the customer's explicit maximum-bonus requirement.
- For a general account recommendation, the November 1–30, 2025 promotional priority applies only when the date is in that range and multiple products meet every stated customer need: Sky Blue first, then Lime Green, then other qualifying products.
- A planned deposit must meet the product's stated qualifying-deposit threshold. Do not treat a planned deposit as completed qualification.
- A product with an unmet tenure, annual limit, rolling limit, or deposit threshold is not an eligible option.

## Evaluator input and output

Run the packaged script through the runtime's script runner. It reads one JSON object from stdin and emits one JSON object on stdout. It uses only the packaged reference file and does not call banking tools.

Important input fields:

- `request_stopped` (boolean): set true whenever the customer stopped or withdrew.
- `current_time` (RFC 3339 timestamp): required to evaluate the rolling nine-day cap and dated promotion.
- `selection_goal`: `maximize_referrer_bonus` or `general_recommendation`.
- `referrer`: authenticated/verified status, exact `tenure_days`, successful `paid_bonus_timestamps`, and `annual_bonus_counts` keyed by program slug.
- `candidate`: planned deposit and the boolean confirmations described in the eligibility gate.
- `requested_account_types` (optional): a list of account slugs to restrict consideration.

Use JSON `null` or omit a field when it is unknown; do not guess. A minimal runnable pause call is:

```sh
printf '%s' '{"request_stopped":true}' | python3 scripts/evaluate_referral.py
```

Validate that stdout is a JSON object and that `status` is one of `stopped`, `needs_verification`, `blocked_ineligible`, `no_matching_program`, or `eligible_options`. Treat `error` as invalid input: correct the case data rather than inventing missing facts.

## Limits and failure handling

- If no tool can verify an item, tell the customer that the referral cannot yet be assessed or submitted; do not claim eligibility.
- A referral record with `REJECTED` or `ERROR` does not itself prove the customer may submit another referral. Check the reason and current rolling-window facts.
- Do not report a bonus as earned until the account opens and all qualification conditions are confirmed.
- Product terms are a supplied policy snapshot. If the runtime provides newer authoritative terms, use those terms rather than silently combining conflicting policies.
