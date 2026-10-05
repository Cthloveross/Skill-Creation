---
name: business-checking-referral-advisor
description: Give safe, evidence-based guidance on business-checking referral bonuses, including conditional product comparisons, eligibility screening, and human escalation. Use when a customer asks which business account maximizes a referral bonus; do not use it to submit a referral or open an account.
---

# Business Checking Referral Advisor

Use this skill to distinguish a **conditional product comparison** from confirmation that a customer or prospective business is eligible. It provides information and escalation only; it never creates a referral, opens an account, transfers funds, or accesses a prospective customer's records.

## Evidence boundary and safety

Use only facts actually present in the current customer conversation or returned by authorized runtime tools. Do not treat separately supplied examples, test context, a question's suggested facts, or another person's information as a customer confirmation.

A product comparison may be stated conditionally before all eligibility facts are known. Do not state that a referral is approved, qualified, or ready to submit until all relevant prerequisites have been confirmed from appropriate evidence.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

If a record lookup is needed, verify the current customer's identity and authority before using it. Do not access a referred business's records without that business's own authorization. General program information may be provided to a third party.

## Responding to a maximize-bonus question

1. Identify the customer's objective. For “maximize my referral bonus,” compare **referrer bonuses**, not welcome bonuses paid to the referred business.
2. Read `references/referral_terms.md` and compare the intended deposit amount and timing against each product's deposit minimum and deadline.
3. If the customer proposes about $30,000 of new money within 90 days, give this bounded comparison when useful:
   - World Blue is the highest documented referrer bonus compatible with that deposit plan: **$300**, provided all eligibility and qualification conditions are ultimately met.
   - True Blue's $350 bonus requires a $50,000 qualifying deposit within 120 days.
   - Beige's $500 reward requires a $100,000 qualifying deposit within 120 days.
4. Clearly label that comparison as conditional. It is not a determination that the referral is eligible, approved, or complete.
5. State the applicable World Blue product terms when discussing it: the referred business must open World Blue and deposit at least $25,000 within 90 days. The referrer tenure threshold is 90 days, measured from the earliest Rho-Bank checking account, regardless of the account currently held.
6. Mention that the referred business may open a product different from the referrer's current product, provided the relevant tenure threshold is met.
7. Do not let a time-limited general account-promotion priority override an explicit request to maximize the referrer's bonus.

For other deposit plans, retain only products whose required deposit, deposit window, referrer tenure threshold, and available product annual cap could be met, then identify the largest referrer bonus among those candidates. Use the helper for a deterministic assessment when structured facts are available.

## Eligibility required before a firm recommendation or referral action

Resolve or actively state each material condition below. Unknown means unknown; do not infer a confirmation from approximate or unrelated statements.

1. Referrer tenure from the exact opening date of the earliest Rho-Bank checking account.
2. No more than two successful referral bonuses in the preceding rolling nine days across all checking products, using exact timestamps when a history check is needed.
3. The selected product's calendar-year bonus count is below that product's annual cap.
4. The referred LLC is a new Rho-Bank customer: no existing checking or savings account and no account closed in the prior 12 months.
5. The LLC has a different registered address and a different primary owner/primary authorized-signer SSN from every existing Rho-Bank business account as applicable.
6. The qualifying deposit is new money, not a transfer from another Rho-Bank account, and is planned within the selected product's window.
7. No incompatible new-account promotion or sign-up bonus will be combined with the referral; only one referral code will be used.
8. Both accounts are or will remain in good standing.

Also explain, where relevant, that the qualifying deposit must remain in the account for at least 30 days after the qualifying period ends, and a referred account closed within 90 days may cause a bonus clawback. Do not promise payment.

If facts are unresolved, either ask concise questions for the unresolved conditions or give only the conditional comparison above. Never proceed to submit a referral based on incomplete screening.

## Customer-requested human transfer

Honor an explicit request to speak with or be transferred to a human agent. Do not delay the requested transfer merely to collect more facts or run an advisory script.

When the transfer is needed because account-opening dates, referral-history timestamps, or other referral eligibility information cannot be verified through the available workflow, call `transfer_to_human_agents` once with:

- `reason`: `specialized_department_required`
- `summary`: a concise, factual description that the customer seeks referral-bonus eligibility help and needs verification of the earliest checking-account opening date and any other unresolved referral conditions.

Do not claim the referral has been approved before or after transferring. If appropriate, give the conditional comparison before the transfer, then confirm that the handoff was requested. If the customer requests a human without a specific stated reason, use `customer_requests_human_no_specific_reason` instead.

## Deterministic assessment helper

Run the packaged helper only after structured facts are available:

```sh
python3 scripts/assess_referral.py < request.json
```

The script reads one JSON object from standard input and writes one JSON object to standard output. It makes no network calls and takes no banking action.

### Input schema

- `as_of` (required): ISO-8601 timestamp with an explicit UTC offset.
- `proposed_deposit` (required): object with `amount` (number or decimal string), `within_days` (non-negative integer), and `new_money` (boolean).
- `general` (required): `referred_is_new_customer`, `different_registered_address`, `different_primary_owner`, `no_promotion_stacking`, `referrer_good_standing`, and `referred_good_standing` booleans; `referrer_checking_tenure_days`; `rolling_bonus_timestamps` as offset-bearing ISO timestamps; and `annual_bonus_counts` mapping product IDs to successful calendar-year bonus counts.
- `programs` (required): product objects containing `id`, `referrer_bonus`, `deposit_min`, `deposit_window_days`, `tenure_days`, and `annual_cap`.

The output includes general blockers, missing confirmations, product-level blockers, and a `recommendation` only when every general gate passes and at least one product qualifies. Interpret a missing recommendation as a reason to withhold a firm eligibility conclusion, not as a denial.

### Validation before responding

- Keep approximate customer recollections distinct from verified dates and timestamps.
- Count the rolling nine-day limit across products, but apply annual caps separately by product.
- Ensure every stated dollar amount for the customer is a referrer bonus, not a referred-business welcome bonus.
- Name unresolved new-customer, owner, address, promotion, and good-standing conditions when they have not been confirmed.

## Separate account-opening workflow

Referral guidance is not account opening. If the prospective business chooses to apply, it must participate directly and authorize its own application. Treat opening as a separate banking action: verify identity; confirm verified-customer status, at least one OPEN personal checking account, no more than six business checking accounts, no CLOSED accounts, and at least $500 in the existing checking account; confirm the desired account class; then use the authorized account-opening workflow.
