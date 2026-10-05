---
name: credit-card-referral-link
version: 1.0.0
description: Safely handle a request for a credit-card referral link. Use when a customer names a card and/or referral terms and wants to share a referral link. The skill verifies that the exact card offer and claimed terms are documented, checks applicable eligibility and rolling referral limits, and only then gives the customer—not the agent—the referral-link tool.
---

# Credit Card Referral Link

## Scope and governing facts

Use this workflow for credit-card referral-link requests. Card participation, bonus amounts, and qualifying requirements vary by card. General information about referrals is not proof that a particular card has an active referral offer.

Documented general restriction: a customer can receive at most **two successful referral bonuses in any rolling seven-day window**, across all credit-card types. A third or later referral in that window is automatically denied and cannot be reinstated within that window.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Required inputs and available tools

At runtime, obtain the customer’s requested exact card name and any claimed offer terms. Search the available knowledge base or supplied card-offer materials for an active referral program for that exact card. A customer-provided letter, recollection, or general referral article alone does not establish the offer.

Where account checks are needed, use the normal banking tools only after identity verification. The available tools commonly include:

- `get_user_information_by_id`, `get_user_information_by_name`, or `get_user_information_by_email` to retrieve identity data after receiving an appropriate identifier.
- `log_verification` after matching two of date of birth, email, phone number, and address, with the current timestamp.
- `get_credit_card_accounts_by_user` to confirm ownership of the exact card.
- `get_referrals_by_user` to evaluate referral history and the rolling limit.
- `give_discoverable_user_tool` to pass an approved self-service tool to the customer.

Never use an agent-discoverable tool, an account-change tool, or another person’s identifier to generate a referral link.

## Workflow

1. **Identify the exact offer before any referral-link action.**
   - Search the available documentation for the exact card name and an active referral program.
   - Compare every material term the customer states (bonus, qualifying spend, timeframe, and eligibility conditions) against the exact card documentation.
   - Do not infer missing terms from a different card, a general referral page, or a customer communication.

2. **Stop for an undocumented or mismatched offer.**
   If no active program for the named card is documented, or the claimed terms do not match the documented program, do not provide a referral-link tool and do not generate a link. Explain the discrepancy neutrally. Do not transfer to a human solely because the offer is unavailable, undocumented, or mismatched.

   State only supported general information: offers and requirements vary by card, a card needs an active referral offer, and the limit is two successful referral bonuses in a rolling seven-day window across card types. Do not repeat an unverified bonus amount, spend threshold, or time period as if it were valid.

3. **For a confirmed offer, complete required prerequisites.**
   Before accessing account-specific records or enabling the customer’s link generation:
   - Verify identity by matching two of the four identity fields and call `log_verification` with all required fields and the current time.
   - Confirm the verified customer owns or is authorized for the exact card and is product-eligible under the documented offer.
   - Confirm all documented offer conditions, fees if any, and any required acknowledgements.
   - Retrieve referral history and identify only referrals that are confirmed successful referral bonuses. Determine whether two such bonuses fall in the preceding rolling seven-day interval. If timestamps are available, run `scripts/assess_rolling_referral_limit.py` as described below.
   - If history, eligibility, or timing cannot be verified, do not assume eligibility or provide the tool. Explain what cannot be verified and any safe next step supported by the available documentation.

4. **Stop when automatic denial is expected.**
   If the customer already has two successful referral bonuses in the rolling seven-day window, explain that an additional referral would be automatically denied. Do not provide the referral-link tool and do not transfer solely for that denial. If available, state that the customer must wait until enough time has passed for the count to drop below two; do not promise an exact time unless the relevant successful-bonus timestamps are verified.

5. **Provide the self-service link tool only when all checks pass.**
   Use `give_discoverable_user_tool` to pass the customer the tool named `get_referral_link`. The agent must not call or generate the link on the customer’s behalf.

   Tell the customer to run it themselves with:
   - their own `user_id`; and
   - the exact, confirmed card name.

   The intended user-side call is:
   ```text
   get_referral_link(user_id: str, card_name: str)
   ```
   A successful call creates a referral record with status `NO_PROGRESS`; the referred person may then use the resulting link to apply. Reiterate the confirmed card’s documented terms and the two-successful-bonuses rolling-seven-day cap.

## Customer-facing response patterns

**Undocumented or mismatched offer:**

> I can’t provide a referral link for that offer because I can’t confirm an active, documented referral program for the exact card and terms described. Referral offers and qualifying requirements vary by card. The documented general limit is two successful referral bonuses in any rolling seven-day period across all card types.

**Confirmed offer, but cap reached:**

> You already have two successful referral bonuses in the relevant rolling seven-day window, so another referral would be automatically denied. Please wait until the rolling count drops below two before trying again.

**Confirmed and eligible:**

> Your card’s documented referral offer is confirmed. I’ve made the referral-link tool available for you to run yourself. Use your own user ID and the exact card name. [Repeat the documented card-specific terms.] A successful link-generation request creates a `NO_PROGRESS` referral record, and the person you refer can use the link to apply. You can receive no more than two successful referral bonuses in any rolling seven-day period across all card types.

## Rolling-limit helper

`scripts/assess_rolling_referral_limit.py` accepts JSON on standard input and emits JSON on standard output.

Input schema:
```json
{
  "now": "ISO-8601 timestamp with UTC offset",
  "successful_bonus_timestamps": ["ISO-8601 timestamp with UTC offset"]
}
```

Only supply timestamps for referrals whose bonus status has been confirmed as successful. The script counts timestamps in `(now - 7 days, now]`. A `would_be_automatically_denied` result of `true` means the referral-link tool must not be provided. An `ok: false` result means the time data is unusable; treat the limit as unverified and do not provide the tool.

Example invocation through the packaged-script runtime:
```json
{
  "relative_path": "scripts/assess_rolling_referral_limit.py",
  "input_json": {
    "now": "2025-01-15T12:00:00-05:00",
    "successful_bonus_timestamps": []
  }
}
```

Validate that `ok` is true, the count is based only on confirmed successful bonuses, and `would_be_automatically_denied` is false before progressing to the self-service tool step.
