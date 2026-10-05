---
name: savings-card-net-return-recommendation
version: 1.0.0
description: Recommend and, only after required verification and authorization, help open a Rho-Bank personal savings account and arrange funding when a customer wants to maximize one-year savings APY less a prospective credit card annual fee. Use for static-balance comparisons of documented savings/card combinations.
---

# Savings and credit-card net-return workflow

Use this skill when a customer wants a single savings-account and credit-card recommendation based on one-year net return, or wants to proceed with opening the recommended personal savings account.

## Scope and calculation

This workflow compares a stated, constant savings balance for one year. APY is already an annualized yield, so calculate projected one-year interest as:

`deposit × (combined APY / 100)`

Then calculate:

`net return = projected interest − one annual card fee`

Do not compound an APY again. A card bonus is additive to the base savings APY only when the product documentation says it applies. Multiple credit-card APY bonuses never stack: use only the highest applicable card bonus. Do not assume an undocumented bonus, fee waiver, rate, account-opening minimum, or maintenance requirement.

Use `scripts/compare_net_return.py` for deterministic arithmetic and filtering. Its JSON input is:

```text
{
  "deposit": number or decimal string,
  "candidates": [
    {
      "id": "stable descriptive identifier",
      "base_apy_pct": number or decimal string,
      "card_bonus_pcts": [number or decimal string],
      "annual_card_fee": number or decimal string,
      "opening_minimum": number or decimal string,
      "ongoing_minimum": number or decimal string,
      "eligible": true,
      "notes": ["optional documented qualification or uncertainty"]
    }
  ]
}
```

It emits JSON containing `ranked`, `rejected`, and `best`. A candidate is rejected if its stated deposit does not meet its opening or ongoing minimum, or if `eligible` is false. An empty `card_bonus_pcts` means no documented bonus. `eligible` must be false when a mandatory condition is not met and should not be set true merely because it has not yet been checked.

Example executor invocation format:

```text
run_skill_script(relative_path="scripts/compare_net_return.py", input_json=<schema above>)
```

Validate that the resulting `best` candidate is not null, that its total APY is supported by the cited product records, and that every excluded alternative has a documented exclusion reason. Present projected earnings as an estimate based on a constant balance; actual daily balances, approval, card status, taxes, and unspecified fees can change the result.

## Product facts currently supported by the packaged evidence

Consult `references/documented_product_facts.md` before constructing candidates. For a $20,000 static balance, the documented balance-qualified leading comparison is conditional on product approval and savings-opening eligibility:

- **Silver Account + EcoCard**: Silver's $20,000 balance is in its 4.0% tier; EcoCard adds 2.2%; EcoCard has a $50 annual fee. This projects $1,240 interest and $1,190 net return.
- **Gold Account + EcoCard**: 5.5% plus 0.6%, less the $50 annual fee, projects $1,170 net return.
- Gold Plus, Platinum, and Platinum Plus documented minimums make them unsuitable for a $20,000 static-balance plan as specified in the reference.

Accordingly, where the customer has a $20,000 static balance and no unverified condition changes the result, recommend **Silver Account plus EcoCard** as the highest documented, balance-qualified net-return combination. State that EcoCard approval remains subject to its application process and that the savings account cannot be opened until all savings eligibility checks pass. Do not claim that a card is approved or that a savings APY bonus is active before the products are opened, approved, linked, and in good standing.

## Mandatory banking safeguards

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

A recommendation or explanation alone is not authorization to apply for a credit card, open a savings account, or transfer funds. Do not perform any banking action until all applicable checks below and the customer's explicit authorization are complete.

## Customer interaction and execution procedure

1. **Identify and verify the customer.** Locate the customer record using the customer-provided name or email. Obtain confirmation of two of the four identity fields (date of birth, email, phone number, address) without volunteering those values. Retrieve the current timestamp and call `log_verification` only after the two-field confirmation succeeds. Record the verified customer ID.

2. **Clarify the comparison assumptions.** Confirm the amount to remain in savings, intended one-year horizon, and that annual card fees should be deducted. Explain that the recommendation assumes the stated balance remains constant and does not include rewards from card spending, taxes, or fees not documented for the comparison.

3. **Build only documented candidates.** Read the product reference and applicable current product terms. For each candidate, capture base APY for the customer’s balance tier, documented applicable card bonus, one annual fee, opening minimum, ongoing minimum, and all mandatory qualification conditions. Mark candidates ineligible if the balance is below either required minimum or if known requirements fail. Use the comparison script; do not manually add multiple card bonuses.

4. **Provide one clear recommendation.** State the selected account and card, the base APY, single card bonus, combined APY, annual card fee, projected interest, and projected net return. Cite material conditions, including balance thresholds and card approval requirements. If no fully documented and balance-qualified candidate remains, explain why and request the information or product terms needed to make a recommendation rather than guessing.

5. **Obtain separate authorizations.** Ask separately whether the customer wants to (a) submit the credit-card application through the supported customer application channel and (b) open the named savings account. Card applications require the standard identity and income information described in the applicable card terms. The available banking action workflow does not provide an agent credit-card-opening tool; do not imply an application was submitted when no supported tool is available.

6. **Before opening a personal savings account, verify every savings prerequisite.** Confirm all of the following from authoritative account records: identity verified; at least one active Rho-Bank checking account; checking tenure of at least 14 days; fewer than five existing personal savings accounts; no accounts in collections; and no negative account balances. Also confirm the selected official `account_class` exactly, that the customer has authority over the profile and source account, all applicable product requirements and fees, and the proposed funding amount.

   If any prerequisite fails or cannot be verified, do not open the account. For a five-account limit, tell the customer they have reached the maximum. For insufficient tenure, tell them when eligibility begins if the opening date is available. For collections or negative balances, explain that the issue must be resolved first.

7. **Open only after authorization and eligibility.** Unlock `open_bank_account_4821`, then call it with the authenticated `user_id`, `account_type` set to `savings`, and the full official class name ending in `Account`. For this recommendation the exact class is `Silver Account`. Confirm the returned new account identifier and details before discussing a transfer.

8. **Arrange the opening deposit only with explicit transfer authority.** Ask whether the customer wants an immediate transfer and identify the exact checking source, new savings destination, and amount. Before transfer, verify ownership of both accounts, available balance, transfer fees, transfer limits, cutoffs, and final recipient/account details. Unlock and call `transfer_funds_between_bank_accounts_7291` only after these checks and explicit confirmation. Do not transfer based solely on a prior statement of savings intent.

9. **Close the interaction accurately.** If funded, confirm the account details and transfer status. If the customer declines immediate funding, state that they have 30 days to fund the account by internal transfer or external deposit or it will be closed. Never claim that a card APY bonus is active until the approved, active card and savings account are linked under the same customer profile.

## Failure handling

- Missing identity confirmation, eligibility records, authority, source balance, or account data: pause the action and request or obtain the missing verification through supported records.
- Unsupported action or unavailable tool: do not fabricate completion. Explain the limitation and direct the customer to the supported application or servicing channel.
- Script validation error: correct the candidate data from authoritative product documentation; do not substitute estimated terms.
- A change in balance, terms, or card availability: recompute the comparison using current documented inputs before making a final recommendation.
