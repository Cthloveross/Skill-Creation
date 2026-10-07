---
name: travel-checking-account-guidance
version: 1.0.0
description: Assist a banking customer who is comparing checking accounts for international ATM use and early direct deposit. Use documented account terms, resolve relevant fee caveats, confirm eligibility before opening, and do not open an account without the customer's explicit selection.
---

# Travel checking account guidance

Use this Skill when a customer needs a checking-account recommendation for travel, especially where foreign ATM costs and early direct deposit matter.

## Operating rules

1. Treat account documentation and the customer conversation as the source of truth. Do not infer that a $0 foreign-ATM fee also removes unrelated out-of-network fees, ATM-owner surcharges, conversion charges, maintenance fees, or balance conditions.
2. Distinguish clearly between:
   - the bank's foreign ATM withdrawal fee;
   - a separately stated out-of-network ATM fee;
   - third-party ATM-operator surcharges;
   - foreign-exchange conversion markup; and
   - ATM-fee rebates and their caps.
3. Consider the customer's stated ability to meet opening-deposit and ongoing-balance requirements. Do not recommend a benefit that requires a condition the customer says they cannot meet.
4. Do not claim an account has been opened, or perform opening actions, until the customer explicitly chooses the account and asks to proceed.
5. Provide a concise answer to the customer's current question first. A recommendation should explain material caveats rather than promising that all ATM use will be free.

## Decision method

At runtime, extract documented terms for each plausible account:

- foreign ATM bank fee and any formula/minimum;
- separate out-of-network fee;
- third-party-fee treatment and rebate cap;
- early-direct-deposit availability;
- required opening deposit, minimum balance, and maintenance fee/waiver condition;
- foreign conversion markup when relevant; and
- any stated daily ATM limit relevant to the trip.

Eliminate options whose required deposit/balance the customer cannot meet. Among the remaining options, prefer the lowest predictable bank-side ATM cost while satisfying early direct deposit. Explain any residual variable charges and relevant rebate cap.

Use `scripts/compare_offers.py` for a structured comparison when the account terms are available as JSON. The script is advisory only; the executor must still cite and communicate the actual documented conditions.

## Responding to a confirmation request

When the customer asks whether a stated foreign ATM fee applies abroad/in foreign currency and whether early direct deposit has a given availability:

1. Answer each point directly from the relevant account documentation.
2. State the exact scope of the documented foreign-ATM term (for example, worldwide or foreign-currency withdrawals) only if the documentation says so.
3. Immediately disclose separately documented out-of-network charges, third-party operator charges, conversion markup, and rebate terms that can affect the total cost.
4. State the maintenance-fee waiver requirement if the recommendation depends on it.
5. Invite the customer to explicitly choose the account if they want it opened; do not treat an inquiry as consent.

## Opening workflow after explicit consent

Only after the customer selects a specific personal checking account and requests opening:

1. Identify the customer and verify identity using two of the four supported fields (date of birth, email, phone number, address).
2. Obtain the current timestamp with `get_current_time` and record successful verification with `log_verification` using all required identity fields.
3. Confirm the documented eligibility requirements: verified customer, applicable age requirement, no more than the permitted number of personal checking accounts, and no disqualifying checking closure in the stated lookback period. For account-specific age restrictions, apply the account-specific rule as well.
4. Confirm the customer has selected the full official `account_class` name ending in `Account`.
5. Use the documented normal account-opening banking tool only after all prerequisites pass. If the opening tool is discoverable, unlock it first and call it with the exact runtime-supported schema; do not invent arguments.
6. Report the outcome accurately. If eligibility data or tool access is missing, explain that opening cannot yet be completed and request only the information needed.

## Script interface

`python3 scripts/compare_offers.py` reads one JSON object from standard input and emits one JSON object to standard output.

Input schema:

```json
{
  "customer": {
    "can_meet_opening_deposit": true,
    "can_meet_minimum_balance": true,
    "needs_early_direct_deposit": true
  },
  "offers": [
    {
      "name": "Official Account Name",
      "foreign_atm_bank_fee": {"kind": "flat", "amount": 0},
      "out_of_network_atm_fee": {"kind": "flat", "amount": 0},
      "early_direct_deposit_days": 0,
      "opening_deposit_required": 0,
      "minimum_balance_required": 0,
      "monthly_maintenance_fee": 0,
      "atm_rebate_cap_monthly": 0,
      "notes": []
    }
  ]
}
```

Fee objects may use `kind` of `flat`, `percent`, `percent_min`, `percent_max`, `allowance_then_flat`, or `unknown`; preserve any nonnumeric details in `notes`. The script filters known-ineligible offers and ranks eligible offers by a conservative, documented bank-fee score. Its result is not a substitute for explaining fee scope and third-party charges.

## Validation

Before replying, check that the response:

- answers each question actually asked;
- does not conflate a bank fee with an ATM-operator fee or rebate;
- includes balance/maintenance consequences relevant to the recommendation;
- makes no unsupported promise about total ATM costs; and
- contains no account-opening claim unless an opening tool has actually returned success.
