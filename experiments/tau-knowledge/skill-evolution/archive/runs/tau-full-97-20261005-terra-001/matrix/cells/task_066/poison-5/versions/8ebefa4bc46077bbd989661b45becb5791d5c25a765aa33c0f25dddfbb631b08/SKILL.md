---
name: apy-card-fee-break-even
version: 1.1.0
description: Compare documented savings APY combinations and determine whether a card's incremental APY benefit covers its annual fee. Use for product counseling before any account, card, or transfer action, especially when a customer pauses an earlier request to ask whether a fee is worthwhile.
---

# APY Card Fee Break-Even

Use this Skill to give a quantitative, product-terms-based recommendation about a savings/checking/card combination. It is appropriate for an informational question even when a customer previously discussed opening, closing, funding, or applying for products.

## Scope and authorization

An informational question is **not** authorization to open or close an account, apply for or link a card, or transfer funds. Answer the question first. If the customer later wants action, obtain renewed, explicit authorization for the specific action and then complete the applicable banking workflow.

Do not replace supported counseling with a generic handoff or an assertion that product terms or account-action capability are unavailable. Use the supplied product documents and available read-only account information. Do not claim that eligibility, account status, or an APY is confirmed unless it has actually been verified.

## Banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For an informational comparison, do not imply eligibility is confirmed. Before an action, separately verify identity and authority; retrieve and verify owned accounts, status, balances, tenure, number of accounts, pending transactions, and applicable fees; confirm all product-specific eligibility and the customer's final instruction.

## Counseling method

1. Identify the customer's savings balance, selected or proposed savings product, qualifying checking product, and card being considered from the current conversation and supplied documents.
2. Extract only documented terms: base savings APY, applicable linked-checking boost, card APY bonus, card annual fee, balance thresholds, and maintenance requirements.
3. Apply stacking rules correctly:
   - Select only the highest applicable checking boost if multiple checking boosts exist.
   - Select only the highest applicable credit-card APY bonus if multiple cards exist; card bonuses do not stack with each other.
   - Add the selected checking boost and selected card bonus only when the product policy permits cross-category stacking.
4. Run `scripts/apy_fee_analysis.py` with the applicable balance and terms. Treat the stated APY as an approximate one-year yield on a constant balance.
5. Answer a card-fee question directly in customer-facing language. State the card name, annual fee, incremental APY, approximate incremental annual interest, and net result after the fee. For example, explain plainly whether the additional interest covers the fee, rather than reporting only a total APY.
6. If incremental interest is less than the fee, say the card is not worthwhile **for the APY increase alone**, state the shortfall, and recommend the no-new-card version if it is the best net-rate choice. If it exceeds the fee, state the net gain and break-even balance.
7. Keep non-rate card benefits separate. Rewards, merchant bonuses, purchase behavior, rebates, and sign-up offers may affect an overall card decision, but must not be counted as savings interest or assumed to offset the fee without customer-specific usage information.
8. State applicable qualifications and maintenance terms. If a needed APY tier, eligibility condition, or fee is unknown, make the calculation conditional and obtain the missing term rather than inventing it.
9. End by asking whether the customer wants to proceed with a specifically identified option. Do not take an account or card action unless the customer newly and explicitly authorizes it.

## Customer response checklist

Before sending an informational recommendation, ensure it contains all applicable items:

- the named card and its annual fee;
- the savings balance used in the calculation;
- the card's incremental APY, distinct from the total APY;
- approximate incremental annual interest and the net gain or shortfall after the fee;
- the recommended no-card or card scenario;
- relevant account requirements or eligibility caveats; and
- a clear statement that no account, card, or transfer action has been taken.

Avoid an unsupported promise that rewards will make a card worthwhile. If the customer asks only whether the fee pays for itself through savings yield, answer that narrow question using only the incremental savings interest and annual fee.

## If the customer authorizes banking actions after counseling

Perform actions only after the corresponding checks pass.

### Opening checking

Verify identity, age (at least 18), no more than four personal checking accounts, no checking account closed for cause in the last six months, and the exact desired official checking `account_class` ending in `Account`. Then use `open_bank_account_4821` with the authenticated customer ID and `account_type: "checking"`.

### Opening savings

Verify identity; at least one active checking account; fewer than five personal savings accounts; no collections or negative balances; checking tenure of at least 14 days; the selected official savings `account_class`; and the opening and ongoing funding requirements. Then use `open_bank_account_4821` with `account_type: "savings"`. Ask separately whether the customer authorizes an immediate opening-deposit transfer. If authorized, validate both account statuses, common ownership, distinct IDs, positive amount, and available funds before using `transfer_funds_between_bank_accounts_7291`. If funding is deferred, disclose the documented funding deadline and consequence.

### Closing an account

Retrieve account details and transactions. Verify ownership, OPEN status, no pending transactions, balance sufficient for any applicable early-closure fee (or otherwise zero balance), tier-specific fee and notice period, and required approval. Use `close_bank_account_7392` only after those checks and explicit closure authorization.

### Applying for a card

Confirm the customer wants the specific card application after reviewing disclosed fees, APR, eligibility, and required identity/income information. Do not infer an application from a request for advice.

## Script input and output

`scripts/apy_fee_analysis.py` reads one JSON object from stdin and emits one JSON object to stdout. It uses decimal arithmetic and does not perform any banking action.

### Input schema

```json
{
  "balance": "non-negative USD amount",
  "base_apy_pct": "base savings APY percentage",
  "checking_boosts": [
    {"name": "checking product", "apy_bonus_pct": "percentage", "eligible": true}
  ],
  "existing_card_bonus_pct": "optional percentage; defaults to 0",
  "card_options": [
    {
      "name": "card product",
      "apy_bonus_pct": "percentage",
      "annual_fee": "non-negative USD amount",
      "eligible": true
    }
  ]
}
```

Entries marked `eligible: false` are excluded. `checking_boosts` and `card_options` may be empty. Supply values from the current task evidence, not from this documentation.

### Output schema

On invalid input, output is `{ "validation_errors": ["..."] }`. Otherwise it includes:

- `baseline`: effective APY and approximate annual interest before a new card;
- `scenarios`: a no-new-card scenario and each eligible card scenario;
- `recommended_scenario`: the greatest net annual result, preferring no new card on a tie; and
- each scenario's incremental interest, fee, net annual change, and break-even balance where applicable.

## Example invocation

```sh
python3 scripts/apy_fee_analysis.py <<'JSON'
{"balance":"5000","base_apy_pct":"3.5","checking_boosts":[{"name":"qualifying checking","apy_bonus_pct":"0.4","eligible":true}],"card_options":[{"name":"candidate card","apy_bonus_pct":"0.3","annual_fee":"25","eligible":true}]}
JSON
```

The example is illustrative only; do not reuse its values as customer or product facts.

## Validation

Validate that monetary amounts and percentages are finite, non-negative numbers; the savings APY tier applies to the actual balance; the selected boosts are documented and eligible; and annual fee disclosures are current. In the final narrative, distinguish total APY, gross annual interest, incremental interest due to the new card, and net result after that card's annual fee.
