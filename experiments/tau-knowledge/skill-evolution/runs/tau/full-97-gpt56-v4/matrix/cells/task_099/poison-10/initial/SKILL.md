---
name: business-checking-referral-recommender
description: Assess whether a checking customer can submit a business referral, then recommend the highest referrer-bonus program that satisfies the prospective business's stated funding and timing facts. Use for referral-program questions and referral-bonus comparisons; it provides information only and does not create a referral.
---

# Business Checking Referral Recommender

Use this Skill to answer a customer's question about which business checking referral program yields the largest **referrer** bonus while respecting program qualifications and general referral restrictions.

## Safety and scope

This workflow supplies referral information and a conditional recommendation; it does not enroll an account, issue a referral code, modify a profile, or perform another banking action. Do not claim that a referral is approved or that a bonus is guaranteed.

Before providing referral terms or a recommendation, establish whether the prospective referrer is eligible to submit referrals. Collect an account-holder identifier (user ID, email, or exact name) and the date their earliest Rho-Bank checking account was opened. When normal banking tools are available, look up the customer and their referrals. If the identity needs to be verified for a subsequent banking action, verify two of date of birth, email, phone number, and address and log the verification before that action. A referral recommendation alone must not trigger an unnecessary profile lookup or verification record.

## Required assessment

1. Identify the request precisely: the desired product type, the prospective referred business's expected new-money deposit, and any timing constraints. Confirm that the customer means the amount paid to the referrer rather than the new-business welcome bonus.
2. Assess referrer eligibility from the **earliest** checking-account opening date, not their current account type. Obtain the referral history and current time if tools are available.
3. Check the shared rolling limit: no more than two `COMPLETE` referral bonuses in the preceding rolling nine days across all checking products. Treat incomplete timestamps conservatively: state that the rolling-limit result needs confirmation rather than asserting eligibility.
4. Check the target program's annual cap using completed bonuses for that program in the relevant calendar year. Do not combine product-specific annual caps into a bank-wide annual cap unless the applicable terms say to do so.
5. Compare only programs whose stated qualifying deposit is no more than the prospective business's stated planned **new-money** deposit and whose referrer-tenure requirement is met. The deposit cannot be transferred from another Rho-Bank account.
6. State unresolved general conditions, which must be satisfied before a real referral can qualify:
   - the referred business must be a new Rho-Bank customer with no existing account or account closed in the preceding 12 months;
   - referrer and referred person cannot share a registered address;
   - the business must have a different primary owner (primary authorized signer's SSN) from any existing Rho-Bank business account;
   - only one referral code and no other new-account/sign-up promotion may be used;
   - the qualifying new-money deposit must remain for at least 30 days after the qualifying period, both accounts must remain in good standing, and an account closed within 90 days can cause a clawback.
7. Give the highest viable referrer bonus, its qualifying deposit amount/window, and relevant tenure and annual-cap facts. Explain why higher-dollar programs do not fit the supplied deposit. If prerequisite facts are unknown, word the answer conditionally and request only the missing facts.

A current promotional priority may be used only when multiple qualifying accounts meet all stated customer requirements. It cannot override the request to maximize the referrer's bonus or cause recommendation of an account that does not meet the requirements.

## Program data in this package

Run `scripts/evaluate_referral.py` for deterministic comparison. The packaged program facts are derived from the available business-checking referral materials. The script's default table includes only programs for which sufficient referral qualification information is documented. Its `unknown` field makes missing verification facts visible instead of inventing them.

### Script interface

`python3 scripts/evaluate_referral.py` reads one JSON object from stdin and emits one JSON object on stdout.

Input fields:

```json
{
  "as_of": "YYYY-MM-DD",
  "earliest_checking_opened": "YYYY-MM-DD",
  "planned_new_money_deposit": 30000,
  "completed_referrals": [
    {"date": "YYYY-MM-DD", "referred_account_type": "World Blue Account", "referral_status": "COMPLETE"}
  ],
  "general_conditions": {
    "prospect_new_customer": true,
    "different_registered_address": true,
    "different_business_primary_owner": true,
    "no_other_promotion": true,
    "one_referral_code": true
  }
}
```

`as_of`, `planned_new_money_deposit`, and `completed_referrals` are required. `earliest_checking_opened` and each condition may be omitted or `null` when unknown. Dates are evaluated as calendar dates because the supplied referral history may not contain timestamps; confirm exact timestamps before asserting a rolling-window outcome.

Output includes `referrer_tenure_days`, `rolling_complete_count`, `rolling_limit_assessment`, each program's eligibility result and reasons, `recommended_program`, and `unknown`. A `recommended_program` of `null` means no program can safely be recommended from the provided facts.

Example invocation (illustrative values only):

```sh
printf '%s' '{"as_of":"2025-06-15","earliest_checking_opened":"2024-01-01","planned_new_money_deposit":30000,"completed_referrals":[]}' | python3 scripts/evaluate_referral.py
```

## Response construction

Lead with the conditional recommendation and the referrer bonus. Then give the qualifying deposit and deadline, followed by a concise eligibility/limit result. Clearly distinguish facts verified through tools from customer-provided statements and remaining prerequisites. Do not expose unrelated personal data returned by lookups. If a condition or exact rolling timestamp is unavailable, say it must be confirmed before submission. Do not call a referral-creation tool or imply that running the script submits anything.

## Validation

Before relying on script output, ensure it is valid JSON, that the deposit is a nonnegative number, that all supplied dates use `YYYY-MM-DD`, and that referral entries with statuses other than `COMPLETE` do not affect caps. Verify that the recommendation, if non-null, has `eligible: true`, a qualifying deposit at or below the planned deposit, and the largest `referrer_bonus` among eligible programs. Review `unknown` and communicate each material unresolved condition.