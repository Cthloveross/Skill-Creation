---
name: checking-referral-advisor
description: Advise a Rho-Bank checking customer on the best combined referral bonus for a prospective new customer, while checking referrer eligibility, rolling referral limits, account-specific qualification rules, and unresolved facts before making a recommendation.
---

# Checking Referral Advisor

Use this Skill for requests to compare or recommend checking-account referral offers. It provides information and recommendations only; it does not create referrals, apply codes, open accounts, or move money.

## Required sequence

1. **Collect the minimum facts before recommending an offer.** Ask for a customer identifier (email, user ID, or exact account name) and confirm:
   - whether the prospective customer is new to Rho-Bank with no current account or account closed in the last 12 months;
   - whether they are registered at a different address;
   - their age (and guardian participation if they are under 18);
   - anticipated qualifying new-money deposit amount; and
   - the date or number of days since the referrer's *first* Rho-Bank checking account was opened.

   Do not provide referral terms or a product recommendation before checking that the referrer can participate. Do not expose retrieved personal data such as address, date of birth, phone number, or user ID in the response.

2. **Use normal banking tools to check the referrer.**
   - Look up the user only with the identifier they supplied.
   - Get the current time.
   - Retrieve all referrals for that user.
   - Treat only `COMPLETE` referrals as successful bonuses for the rolling limit and annual program caps. `IN_PROGRESS`, `APPLIED`, `NO_PROGRESS`, `REJECTED`, and `ERROR` do not consume a successful-bonus slot.
   - The rolling limit is at most two successful referral bonuses in the preceding rolling 9 days across all checking products. It is based on exact timestamps. If only a borderline date (rather than a timestamp) is available and the outcome could affect eligibility, state that the limit cannot be confirmed and do not claim eligibility.
   - Use the customer's confirmation of first-checking-account tenure when the available tools do not expose the account-opening date. Tenure is based on the earliest checking account, not current account type.

3. **Evaluate offers with `scripts/rank_referrals.py`.** The script does deterministic product, deposit, tenure, age, annual-cap, and rolling-window screening. It accepts customer facts and referral records and returns eligible, blocked, and unresolved offers. Its output is advisory: the executor must still ensure the facts were actually collected and must not turn a recommendation into a bank action.

4. **Give a concise, conditional recommendation.** Recommend the eligible account with the largest combined referrer plus new-member bonus. State both shares, the combined amount, required deposit and deadline, and any account age rule. Also disclose material conditions:
   - qualifying funds must be new money, not transferred from another Rho-Bank account;
   - qualifying funds must remain for at least 30 days after the qualification period ends;
   - only one referral code/promotion may be applied to the new account;
   - both accounts must remain in good standing; early closure (within 90 days) can result in a clawback.

5. **Handle missing or failed checks safely.** If the referrer is not eligible, has already reached two completed bonuses in the rolling window, meets an account's annual cap, lacks required tenure, or a required prospective-customer fact is unknown, say so plainly. Ask only for the fact needed to resolve the issue. Do not imply that an auto-denied referral can be reinstated inside the same 9-day window.

## Product rules encoded by the helper

| Account | Referrer / new-member bonus | Annual cap | Deposit requirement | Referrer tenure | Special prospective-customer rule |
|---|---:|---:|---:|---:|---|
| Blue Account | $35 / $30 | 5 | $500 within 60 days | 30 days | Standard adult rules |
| Green Fee-Free Account | $20 / $35 | 4 | $300 within 60 days | 30 days | Standard adult rules |
| Light Blue Account | $30 / $20 | 5 | $500 within 60 days | 30 days | Standard adult rules |
| Light Green Account | $15 / $25 | 3 | $100 within 90 days | 14 days | Primary holder must be age 13–24; minors require a guardian |
| Dark Green Account | $40 / $30 | 6 | $1,000 within 60 days | 45 days | Standard adult rules |
| Bluest Account | $75 / $50 | 8 | $2,000 within 90 days | 60 days | Standard adult rules |
| Gold Years Account | $50 / $75 | 6 | $1,000 within 90 days | 30 days | Referred person must be age 62+ |

The standard program restrictions—new customer/no Rho-Bank account in the prior 12 months, different registered address, and age 18+—apply to all products except that Light Green can be opened by an eligible minor with a guardian.

## Helper interface

Run with JSON on standard input and read JSON from standard output:

```json
{
  "current_time": "2025-01-15 12:00:00",
  "expected_deposit": 600,
  "referrer_tenure_days": 40,
  "referred_age": 28,
  "guardian_participates": false,
  "is_new_customer_no_recent_account": true,
  "different_registered_address": true,
  "referrals": [
    {"referral_status": "COMPLETE", "date": "2025-01-04", "referred_account_type": "Blue Account"}
  ]
}
```

`current_time` must be an ISO-like local timestamp (`YYYY-MM-DD HH:MM:SS` is sufficient). `referrals` may use `date` or `timestamp`. Unknown values should be `null` or omitted rather than guessed. The output contains `recommendation`, `eligible_offers`, `blocked_offers`, `unresolved_offers`, `baseline_issues`, and rolling-window findings.

Validate the result before using it: a recommendation must be non-null, have no baseline issues, and list all relevant user-provided facts as sufficient. If the script flags an unresolved rolling window or unknown age, tenure, or baseline eligibility, obtain the fact or explain that no definitive recommendation can yet be made.
