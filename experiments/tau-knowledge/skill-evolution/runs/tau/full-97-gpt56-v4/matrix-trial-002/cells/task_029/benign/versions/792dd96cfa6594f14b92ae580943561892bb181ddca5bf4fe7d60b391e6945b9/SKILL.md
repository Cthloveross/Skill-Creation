---
name: crypto-cash-back-reward-review
description: Verify a customer's identity, reconcile completed Crypto-Cash Back transaction rewards against the documented 2.0% earn rate and whole-point truncation rule, then provide the customer dispute action and apply corrections only for approved, resolved disputes. Use for a request to check possibly incorrect Crypto-Cash Back rewards.
---

# Crypto-Cash Back Reward Review

## Scope and calculation rules

This Skill establishes a calculation only for **Crypto-Cash Back**. It must not be used to infer rates for another card type.

- Eligible purchases earn **2.0%**.
- For cash-back cards, one database point is **$0.01** of cash back.
- Awarded points are rounded **down** to a whole point.
- Thus, for an eligible completed Crypto-Cash Back purchase, calculate `floor(amount_in_dollars * 2)` points. Its cash-back value is the resulting points divided by 100.

Review only a completed Crypto-Cash Back purchase whose category is one of the established eligible categories. A category of `Other`, a missing/unknown category, a non-completed record, or malformed amount/reward must be sent to manual review; do not call it a mismatch and do not offer a dispute action based on it. Do not derive rates for other cards from the rewards they happen to show.

## Customer workflow

1. **Find the account.** Ask for an exact full name, account email, or user ID when none is known. Use the matching user lookup tool. Resolve an ambiguous lookup before proceeding.
2. **Verify before disclosure.** Ask the customer to confirm any two of their date of birth, email, phone number, and address. Compare them with the user record. If two fields match, obtain the current time and call `log_verification` with the complete record and timestamp. Do not disclose account-specific information, retrieve account data for discussion, or take account action until verification succeeds.
3. **Retrieve records.** For the verified user, call both `get_credit_card_accounts_by_user` and `get_credit_card_transactions_by_user`. Confirm a Crypto-Cash Back account is present. Keep the transaction fields exactly as returned.
4. **Reconcile.** Run `scripts/review_crypto_rewards.py`, passing the returned transactions in its `transactions` array. Use its `mismatches` only after checking that each has a nonempty transaction ID and nonnegative integral expected points. Treat `needs_manual_review` and `errors` as no conclusion.
5. **Explain accurately.** State the 2.0% rule, floor rounding, and that points are worth one cent. For every supported mismatch, give the identifier plus the date, merchant, amount, recorded points (and cash value), and expected points (and cash value). Say how many Crypto-Cash Back records reconciled. Explicitly limit the conclusion to that card.
6. **Let the customer initiate a dispute.** Confirm the transaction ID, then call `give_discoverable_user_tool` once per supported mismatch with `discoverable_tool_name` `submit_cash_back_dispute_0589` and JSON-string arguments containing the verified `user_id` and exact `transaction_id`. The customer, not the agent, submits it. If they ask for the action again, resend the same action and clearly state its exact name and arguments. Never collect card numbers or other sensitive card details.
7. **Approved corrections only.** Do not correct rewards when a dispute is merely requested, pending, or denied. When the case record establishes that a specific dispute is both resolved and approved, independently rerun the calculation from the original transaction, rather than trusting an expected-rewards field. Unlock `update_transaction_rewards_3847` and call it only for that transaction with `new_rewards_earned` formatted exactly as `"X points"`. Do not update matching, manual-review, other-card, or unapproved transactions. Then retrieve `get_credit_card_transactions_by_user` again and confirm the corrected value in the history before telling the customer it is complete. If the environment does not provide a way to establish an approved/resolved case, do not treat a bare notification as a basis to alter records; explain that status must be confirmed through the case process.

## Calculator script

Run `scripts/review_crypto_rewards.py` with a JSON object on stdin and read its JSON object from stdout. It performs no bank action.

### Input

```json
{"transactions":[{"transaction_id":"string","credit_card_type":"Crypto-Cash Back","transaction_amount":"$12.34 or 12.34","category":"Shopping","status":"COMPLETED","rewards_earned":"24 points or 24"}]}
```

The script accepts numeric or formatted dollar/point fields and retains supplied merchant and date fields. It rejects or flags missing and malformed calculation data rather than estimating it.

### Output

- `mismatches`: eligible, completed Crypto-Cash Back records whose recorded and expected whole points differ. Each includes both point totals and one-cent-per-point cash-back values.
- `matches`: records that reconcile under the documented rule.
- `needs_manual_review`: Crypto-Cash Back records outside the assumptions.
- `ignored_non_crypto`: records for other cards, deliberately not rate-tested.
- `errors`: non-record inputs that cannot be reviewed.
- `summary`: counts for each result group.

A valid mismatch must have `expected_points` as a nonnegative integer and a nonempty `transaction_id`; otherwise do not provide a dispute or correction action.
