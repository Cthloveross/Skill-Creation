---
name: business-checking-referral-advisor
description: Provides read-only, eligibility-first guidance for business-checking referrals. Use when a checking customer asks whether they can refer a business, asks about referring to the same product they hold, or asks which documented referral option has the largest reward.
---

# Business Checking Referral Advisor

Use this Skill only for **read-only referral eligibility assessment and guidance**. It does not submit a referral, apply a referral code, open an account, or otherwise perform a banking action.

## Governing rules

- A referrer may refer a business to the **same account type** they hold or to a different checking product. The current account type is not an eligibility restriction.
- Referrer tenure is measured from the earliest Rho-Bank checking-account opening, not from the current product's opening date.
- A referrer may receive at most two successful referral bonuses in an exact rolling nine-day period across all checking products. A third referral in that window is denied.
- The prospective referred person must be a new Rho-Bank customer with no existing checking or savings account and no account closed during the past 12 months. The referrer and prospective customer must have different registered addresses.
- For a business referral, the LLC's primary authorized signer must have an SSN different from the primary owner of every existing Rho-Bank business account.
- The prospective referred person must meet the applicable age rule. Business qualification deposits must be external new money, remain for at least 30 days after the qualification period, and cannot be combined with another new-account promotion or a second referral code. Both accounts must remain in good standing.

## Mandatory eligibility-first sequence

The general referral policy requires eligibility review **before** giving a recommendation, comparing products, naming a referral program, quoting bonus amounts, or quoting referral terms.

1. Verify the referrer's identity using two confirmed identity fields, log verification when the normal runtime procedure supports it, and confirm authority, account ownership, and standing.
2. Review referral history for successful bonus timestamps and the relevant annual program counts. Check the rolling nine-day limit before any referral action.
3. Establish the referrer's tenure evidence from the earliest checking relationship.
   - Do not use the current account type as a proxy for tenure.
   - Do not insist on an exact opening date where the customer's supported timeframe plainly establishes the applicable threshold. For example, a mid-July opening reported in mid-November is sufficient evidence for a 90-day threshold when there is no boundary ambiguity.
   - Obtain an exact date only when the reported timeframe is ambiguous, a higher threshold could affect the result, or an account record is available and must be reconciled.
4. Before any product advice, identify and assess the **prospective customer**. Obtain their full name or email and confirm whether they will be the new LLC's **primary authorized signer**. Then verify new-customer status, registered-address separation, age eligibility, and the different-primary-owner requirement.
5. Confirm planned funds are external new money and check that no competing new-account promotion or additional referral code will be used.
6. Only after both the referrer and prospective-customer gates pass, use `scripts/referral_advisor.py` to compare documented qualifying programs. Present the highest documented referrer reward that satisfies the verified deposit, tenure, annual-cap, and other requirements. State all conditions as contingent; never promise a bonus.

## Handling a same-account-type concern while eligibility is incomplete

When a customer asks why they cannot refer a business to the account type they already hold, answer the misconception directly **without naming a program or giving terms**:

- Explain that holding the same account type does not prevent a referral; eligibility uses the earliest checking relationship rather than the current account type.
- State that the outstanding review concerns the former partner or other prospective customer, not the matching account type.
- Ask for the prospective customer's full name or email and confirmation that they will be the LLC's primary authorized signer.
- Explain that those details are needed to check new-customer status, registered-address separation, and the different-primary-owner rule.
- Do not name products, state bonuses, deposits, program thresholds, or recommend an option until this review is complete.

For the currently supplied scenario, the reported mid-July-to-mid-November relationship is enough to avoid repeatedly requesting an exact date for the plainly satisfied 90-day screen. The unresolved facts are the former partner/prospective customer's identity and whether she will be the LLC's primary authorized signer. Continue to withhold referral recommendations and terms until those facts and the resulting eligibility checks are complete.

## Documented-program selection

After all eligibility facts are confirmed, compare only documented programs whose qualifying deposit is no greater than the proposed external new-money deposit, whose tenure threshold is supported by the evidence, and whose annual cap has not been reached. Rank by referrer reward, highest first.

A promotional account-priority notice may be used only if multiple accounts satisfy every stated customer requirement. It never overrides an explicit request for the largest referrer reward.

Keep distinct:

1. whether the referrer may currently submit a referral;
2. which program would offer the largest documented referrer reward if all qualification steps occur; and
3. post-opening conditions, including account opening, qualifying deposit, deposit retention, and good standing.

## Script interface

Run:

```text
python3 scripts/referral_advisor.py
```

The script reads one JSON object from stdin and emits one JSON object to stdout. It performs no network or banking operations.

Input schema:

```json
{
  "now": "ISO-8601 timestamp with offset",
  "planned_new_money_deposit": 0,
  "referrer": {
    "identity_verified": true,
    "authority_confirmed": true,
    "account_ownership_confirmed": true,
    "account_good_standing_confirmed": true,
    "earliest_checking_opened_at": "optional ISO-8601 timestamp with offset",
    "tenure_days_confirmed": 0,
    "successful_bonus_timestamps": [],
    "annual_successful_bonus_counts": {
      "World Blue": 0
    }
  },
  "prospect": {
    "identity_available": true,
    "primary_authorized_signer_confirmed": true,
    "new_customer_confirmed": true,
    "different_registered_address_confirmed": true,
    "age_eligible_confirmed": true,
    "business_primary_owner_different_confirmed": true,
    "new_money_confirmed": true,
    "no_other_new_account_promotion_confirmed": true,
    "one_referral_code_confirmed": true
  }
}
```

`earliest_checking_opened_at` and `tenure_days_confirmed` are alternative tenure evidence. Supply `tenure_days_confirmed` as a conservative, supported lower bound when an exact date is not needed. `successful_bonus_timestamps` contains only bonuses actually received. `annual_successful_bonus_counts` is a per-program calendar-year count; when a verified empty referral history establishes zero for every program, `annual_successful_bonus_count: 0` may be supplied instead.

The result includes `referrer_gate_passed`, `prospect_gate_passed`, `advice_allowed`, `ranked_programs`, and explicit blockers. Empty rankings are intentional whenever eligibility is incomplete; request the listed facts rather than providing product advice.

## Response and action validation

Before responding, verify that:

- no unknown fact is represented as confirmed;
- referral history and the rolling nine-day cap were checked before any action;
- a clearly satisfied tenure threshold was not blocked solely for lack of an exact date;
- the prospective customer identity and primary authorized signer were requested before advice when missing;
- no recommendation or referral terms were given before all referral eligibility gates passed;
- no referral submission, code application, or account opening was performed; and
- any later bonus discussion remains conditional on all qualification requirements and good standing.

## Separate account-opening or referral-submission requests

This advisory Skill is not authorization to act. Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For a business-checking opening, also verify that the prospective customer is verified, has at least one OPEN personal checking account, has fewer than six business checking accounts, has no CLOSED accounts, and has at least $500 in the existing checking account. If the required normal banking tool or a prerequisite is unavailable, do not attempt the action.
