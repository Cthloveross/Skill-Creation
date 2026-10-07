---
name: business-checking-referral-advisor
description: Safely verifies a checking customer's eligibility before discussing or selecting a business-checking referral option, then identifies the highest documented referrer reward compatible with the proposed deposit and tenure. Use for referral questions, especially when the user asks which business checking product provides the largest referral bonus.
---

# Business Checking Referral Advisor

Use this Skill for **read-only referral guidance and eligibility assessment**. It does not submit referrals, open accounts, apply referral codes, or perform any banking action.

## Policy facts applied by this Skill

- Referral eligibility is based on tenure since the referrer's **earliest Rho-Bank checking account**, not the account type currently held. A customer may refer a business to the same checking product they hold or to a different one, provided all program requirements are met.
- A referrer may receive at most two successful referral bonuses in an exact rolling nine-day window across checking products. A third or later referral in that window is automatically denied and cannot be reinstated during that window.
- The prospective referred customer must be new: no existing checking or savings account and no account closed within the past 12 months; the parties must have different registered addresses. For a business referral, the business's primary authorized signer must have an SSN different from the primary owner of every existing Rho-Bank business account.
- Qualification deposits must be new money, not transfers from another Rho-Bank account, and must remain for at least 30 days after the qualification period ends. A bonus may be clawed back if the referred account closes within 90 days. The referral cannot be combined with another new-account promotion or sign-up bonus, and only one referral code can be used.
- Both accounts must be in good standing for bonus payment.

## Required sequence

1. **Identify the referrer and verify identity before taking any account-specific action.** Ask the customer to confirm two of date of birth, email, phone number, and registered address. Resolve their user record, then call `log_verification` only after two fields match. Confirm the person is authorized to refer from the relevant account and owns that account.
2. **Check referrer eligibility before giving program comparisons, bonus figures, or a recommendation.** Obtain the exact earliest checking opening date and retrieve the referrer's referrals. Count only successful/complete bonus timestamps in the preceding exact nine 24-hour days and determine the relevant calendar-year completed-bonus count. Do not treat an application, in-progress referral, rejection, or an unknown timestamp as a successful bonus.
3. If tenure, the rolling cap, annual count, account ownership/authority, or account standing cannot be confirmed, state that eligibility is not yet confirmed and request only the missing information. Do not select or quote a referral option until the referrer gate is complete.
4. After the referrer gate passes, collect enough information to assess the proposed referral: prospective customer's name or email, confirmation they are the new LLC's primary authorized signer, new-customer status, different address, different business primary-owner SSN, expected external new-money deposit, and whether any other promotion or referral code will be applied.
5. Use `scripts/referral_advisor.py` to calculate the rolling-window result and rank documented programs. Supply facts obtained at runtime; never hardcode a customer's identity, dates, account ownership, or referral history.
6. Clearly separate (a) current eligibility to submit a referral, (b) the program that would pay the largest documented referrer reward if the referred business qualifies, and (c) conditions that remain to be completed after account opening. Do not promise a bonus.

### Same-product question

Only after the referrer eligibility gate is complete, answer a same-product concern directly: the current account product does not disqualify a referral. The controlling tenure is measured from the earliest checking account. Confirm the target program's tenure, annual cap, deposit, and all general restrictions before saying the referral can be submitted.

## Program-selection method

Give the script the planned qualifying deposit, exact time, the earliest checking opening timestamp, completed-bonus timestamps, and the referrer's verified status. It first rejects incomplete referrer gates and then:

1. rejects programs whose tenure or deposit requirement is not met;
2. rejects programs at their documented annual cap;
3. ranks the remaining programs by referrer bonus, highest first; and
4. returns submission blockers separately from the ranked result.

A current promotion that prioritizes a product may be used only when it still satisfies every stated customer requirement. In particular, it cannot replace the highest-paying compatible option when the user's explicit requirement is the largest referrer reward.

### Runnable script interface

`python3 scripts/referral_advisor.py` reads one JSON object from standard input and writes one JSON object to standard output.

Required input fields:

```json
{
  "now": "2025-11-14T03:40:00-05:00",
  "planned_new_money_deposit": 31000,
  "referrer": {
    "identity_verified": true,
    "authority_confirmed": true,
    "account_ownership_confirmed": true,
    "account_good_standing_confirmed": true,
    "earliest_checking_opened_at": "2025-07-15T00:00:00-04:00",
    "successful_bonus_timestamps": [],
    "annual_successful_bonus_count": 0
  },
  "prospect": {
    "identity_available": true,
    "new_customer_confirmed": true,
    "different_registered_address_confirmed": true,
    "business_primary_owner_different_confirmed": true,
    "primary_authorized_signer_confirmed": true,
    "new_money_confirmed": true,
    "no_other_new_account_promotion_confirmed": true,
    "one_referral_code_confirmed": true
  }
}
```

All timestamps must be ISO-8601 timestamps with an offset (or `Z`). `successful_bonus_timestamps` must contain only timestamps for bonuses actually received. Booleans may be `false` or omitted where unknown; the output lists the exact blockers. `planned_new_money_deposit` is a nonnegative numeric amount.

The result contains `referrer_gate_passed`, `rolling_window`, `ranked_programs`, `best_program`, and `submission_blockers`. If the referrer gate does not pass, `ranked_programs` is empty and `best_program` is `null`; the executor must request the listed missing checks rather than reveal a recommendation.

## Validation and response checks

Before responding, ensure that:

- two independently confirmed identity fields were logged before any action, and authority and account ownership are confirmed;
- the exact first-checking date—not the current product's opening date—was used for tenure;
- rolling nine-day and per-program calendar-year limits were checked using complete bonuses only;
- no unknown candidate fact was represented as confirmed;
- a referral is never submitted or account opened from this advisory workflow; and
- bonus payment is described as contingent on every qualification condition and both accounts remaining in good standing.

## If an account-opening or referral-submission action is separately requested

Do not use this advisory Skill as authorization to act. Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For a business checking opening, additionally verify the prospective customer is verified, has at least one OPEN personal checking account, has fewer than six business checking accounts, has no CLOSED accounts, and has at least $500 in the existing checking account. If the runtime lacks the required normal banking tool or any prerequisite cannot be verified, do not attempt the action; explain what remains and use the appropriate supported escalation path only if needed.
