---
name: checking-referral-eligibility-review
description: Safely review checking-account referral eligibility and, only after all required facts are confirmed, compare eligible referral programs by combined bonus. Use for customer questions about referring someone to a Rho-Bank checking account.
---

# Checking referral eligibility review

Use this Skill for informational referral comparisons. It does **not** create a referral, apply a code, open an account, or promise a bonus.

## Safety and prerequisite rule

Before giving a recommendation **or referral-term information**, establish that the referrer is eligible to submit a referral and that the prospective referred customer satisfies the universal eligibility rules. If key facts are unknown, do not name a recommended account or disclose program-specific amounts. Explain which confirmation is still needed and offer to reassess after it is available.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For a read-only referral review, collect or confirm:

1. The referrer's identity and authority. For live tool use, have the customer confirm two identity fields, retrieve the matching profile, obtain the current timestamp, and log verification before accessing account-specific records.
2. The exact date the referrer opened their **first-ever Rho-Bank checking account**. Current account type and later checking accounts do not determine tenure.
3. Complete referral history, including status and bonus timestamps. Only successful/complete bonus events count toward the rolling cap. Exact timestamps are needed when an event might fall within the last nine days.
4. The prospective customer's age, whether they are a genuinely new Rho-Bank customer with no checking, savings, or other account (including an account closed in the last 12 months), and confirmation that their registered address differs from the referrer's.
5. The anticipated qualifying deposit, confirmation that it is new money rather than a transfer from another Rho-Bank account, and any known conflicting new-account promotion.
6. Product-specific eligibility where applicable (for example, age eligibility for Light Green or Gold Years).

Do not infer an unknown age, prior-account history, first-checking opening date, new-money source, address, or promotion status from conversational context.

## Live-review workflow

1. If the interaction is live and identity has not already been verified, request two identity fields. Retrieve the customer only through the declared banking tools, confirm the match, get the current time, and call `log_verification` with the retrieved record and time.
2. Retrieve the referrer's referral history using the verified user ID. Do not treat `IN_PROGRESS`, `APPLIED`, `NO_PROGRESS`, `REJECTED`, or `ERROR` as a received referral bonus.
3. Ask targeted follow-up questions for every missing universal eligibility fact. A different address alone does not establish eligibility.
4. Put verified facts into the JSON schema below and run `scripts/analyze_referral.py`.
5. If the result is `blocked`, send only its `safe_user_message` (optionally phrased naturally) and request the listed confirmations. Do not use the embedded program table to disclose a workaround or a recommendation.
6. If the result is `ready`, explain the top candidate and its conditions. Make clear that the qualifying deposit must be new money, must remain for at least 30 days after the qualifying period, only one referral code and no conflicting new-account promotion may be used, and a bonus may be clawed back if the referred account closes within 90 days. Do not promise payment.
7. Before any later referral submission or other banking action, re-check all prerequisites, recipient details, applicable annual cap, rolling nine-day cap, and required confirmations. Normal banking tools—not this script—perform any bank action.

## Program and limit interpretation

- The rolling restriction is a shared maximum of two received referral bonuses in the prior rolling nine days across all checking account types. It is based on exact bonus timestamps, not calendar weeks. A third referral in that window is denied and cannot be reinstated within that window.
- Annual limits are program-specific and apply to received referral bonuses for the target program in the applicable calendar year.
- A referred person generally must be 18 or older. Light Green is the exception for a qualifying minor with a guardian, but its own primary-holder age range must still be met.
- A referrer may refer a person to a different checking product. Tenure always starts at the first Rho-Bank checking-account opening.
- The script ranks only programs whose stated deposit, tenure, annual-cap, age, and universal prerequisites are established from supplied facts. It does not decide account-application approval.

## Script interface

Run:

```text
python3 scripts/analyze_referral.py < review.json
```

The script reads one JSON object from stdin and writes one JSON object to stdout. Required top-level fields are:

```json
{
  "as_of": "2025-01-01T12:00:00-05:00",
  "identity_verified": true,
  "referrer": {
    "first_checking_opened": "YYYY-MM-DD",
    "referral_history_complete": true,
    "referrals": [
      {"status": "COMPLETE", "account_type": "Blue Account", "bonus_received_at": "2025-01-01T10:00:00-05:00"}
    ]
  },
  "recipient": {
    "age": 30,
    "new_customer_confirmed": true,
    "different_registered_address_confirmed": true,
    "minor_guardian_confirmed": false,
    "no_conflicting_promotion_confirmed": true
  },
  "deposit": {"amount": 600, "new_money_confirmed": true}
}
```

`bonus_received_at` may instead be a `YYYY-MM-DD` date only when it is safely more than nine calendar days before `as_of`; otherwise obtain the exact timestamp. The script emits:

- `review_status`: `blocked`, `ready`, or `no_qualifying_program`;
- `missing_confirmations`: facts that must be obtained before terms can be discussed;
- `rolling_window`: an auditable count and cap result;
- `candidate_ranking`: ranked eligible programs only when review is ready; and
- `safe_user_message`: customer-safe wording appropriate to the result.

Validate that the output parses as JSON, that a `blocked` result has an empty `candidate_ranking`, and that no banking action is initiated from the script output.
