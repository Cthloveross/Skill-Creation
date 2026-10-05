---
name: savings-card-net-return-advisor
description: Advise customers seeking a Rho-Bank personal savings account and credit card combination, compare documented one-year savings interest net of fees, verify savings-opening eligibility, and safely open/fund savings only after the required customer selection and authorization. Use for savings-yield comparisons, Green Account/EcoCard questions, and personal savings-account opening requests.
---

# Savings and Card Net-Return Advisor

## Scope and action boundaries
Use this Skill to recommend documented Rho-Bank savings/card combinations, open a personal savings account when all policy gates are met, and arrange an opening-deposit transfer only when expressly authorized.

A recommendation is **not** a savings-account selection. A request to open savings generally is **not** confirmation of a particular `account_class`. Do not open a savings account until the customer expressly selects the recommended official account class. Do not transfer money merely because an account was opened.

Do not claim that product terms, savings-opening actions, or a documented application path are unavailable when they are supplied in the available knowledge. Do not transfer a customer to a human merely to avoid performing a documented comparison or available savings-account workflow.

This Skill does not approve or open credit cards unless the runtime provides a documented credit-card application/opening action. Explaining an application path must never be represented as submitting an application.

## Runtime facts to obtain
Obtain or confirm at runtime:

- Authenticated customer identity and `user_id`.
- Two verified identity fields (from date of birth, email, phone number, and address), current time, and a successful verification audit record.
- All bank accounts using `get_all_user_accounts_by_user_id_3847`; use returned type, class, status, balance, and opening date.
- Existing card accounts using `get_credit_card_accounts_by_user` when card benefits may already apply.
- Planned savings balance, holding period, whether the balance will remain on deposit, and customer priorities.
- The exact savings class selected by the customer.
- Immediate-funding authorization, source account, and amount only after a savings account is successfully opened.

Never expose account IDs, internal tool parameters, account data not needed for the answer, or internal tool instructions to the customer.

## Required workflow

### 1. Authenticate and obtain authoritative account facts
1. Resolve the customer profile using supplied identifying information. A name lookup or a claimed account is not identity verification.
2. Ask the customer to provide two identity fields without reciting undisclosed profile data. Compare them to the authoritative record.
3. Get the current timestamp and call `log_verification` only after two fields match. Populate the audit call from the authoritative profile and timestamp.
4. Unlock and call `get_all_user_accounts_by_user_id_3847` for the authenticated user. This lookup is mandatory before deciding savings-opening eligibility. Do not substitute an uncertain customer statement for system status or balance data.
5. Unlock and call `get_credit_card_accounts_by_user` when evaluating existing card bonuses. Do not assume the customer has, will receive, or will keep a card just because they request one.

If identity cannot be verified, the all-account lookup fails, or returned information is insufficient to establish a mandatory gate, do not open an account. Explain the blocker and continue with general product education where possible.

### 2. Apply the mandatory savings-opening gates
Before opening a personal savings account, confirm all of the following from verified/profile and all-account data:

- identity is verified and logged;
- the customer has at least one `OPEN` or `ACTIVE` Rho-Bank checking account;
- a qualifying checking account was opened at least 14 days ago;
- the customer has fewer than five personal savings accounts;
- no account is in collections and no account has a negative balance.

If any gate fails or cannot be established, do not call the account-opening tool. State the precise known blocker. For an under-14-day checking account, provide the eligibility date when the opening date is known. For five savings accounts, state that the savings-account maximum has been reached.

### 3. Build a documented comparison
Compare only facts stated in current product documentation. For each candidate, use the customer’s planned balance and horizon to determine:

1. the applicable base APY tier;
2. a card APY bonus only when the documentation explicitly lists it and the customer already holds, or is later approved for, the relevant card under the same profile;
3. a checking-linked boost only for an explicitly listed checking/savings pairing;
4. permitted non-card bonuses only when their documented conditions are met;
5. documented annual card fees, one-time fees, and predictable maintenance fees.

Rules:

- Card bonuses do not stack: use only the highest applicable card APY bonus.
- Checking boosts do not stack: use only the highest applicable qualifying checking boost.
- A non-listed checking/savings pair has no checking-linked APY boost. Never infer one from a similar account name.
- A product whose opening deposit or ongoing minimum exceeds the stated plan is not a feasible recommendation; state why.
- Keep interest-minus-known-fees separate from card spending rewards, welcome bonuses, cash back, points, and nonfinancial benefits. Do not assume spending, qualifying purchases, approval, direct deposit, or subscription enrollment that the customer has not established.
- When sources contain an arithmetic example inconsistent with its stated components, calculate from the components and disclose the correct addition.

Use `scripts/compare_net_return.py` for transparent arithmetic after assembling evidence-backed inputs. It estimates interest as `principal × combined APY × horizon_days / 365`; it is not a daily-balance simulation and does not choose products.

### 4. Essential documented comparison: Green Account and EcoCard
When a stable planned balance can meet Green Account requirements and the customer wants the documented Green/Eco combination, explain these specific documented terms accurately:

- Green Account savings has a **4.0%** base APY. EcoCard adds **0.5%**, producing **4.5%**, not 4.75%.
- Green requires a $100 opening deposit, a $500 ongoing balance, and paperless statements. Interest compounds daily and is credited monthly.
- EcoCard has **no minimum credit-score requirement**. Its application requires standard identity and income information and results in an approval decision or request for additional documentation. Never promise approval.
- EcoCard has a **$50 annual fee** and a 19.99% purchase APR on carried balances. Carrying a balance can materially outweigh savings interest, so recommend paying the statement balance when appropriate rather than treating a card as free yield.
- On a constant $5,000 balance for one year, 4.5% is approximately $225 gross savings interest. Less the documented $50 EcoCard annual fee, the interest-minus-annual-fee estimate is approximately **$175**, before unprovided spending rewards, other fees, taxes, or balance changes.

For a $5,000 plan, explicitly compare material alternatives supported by current documents: Silver Plus earns its 3.0% Tier 1 rate below its $15,000 Tier 2 threshold; its EcoCard bonus is 0.45%. Gold, Gold Plus, Platinum, and Platinum Plus have documented standard ongoing balance requirements above $5,000 unless a separately documented qualification changes the requirement. A Light Blue checking account is not an eligible listed checking pairing for Green Account or Silver Plus and therefore adds no checking-linked boost. Do not make claims about products whose applicable terms are not documented.

### 5. Give the recommendation before requesting a selection
Present a concise customer-facing comparison that states:

- recommendation and reason;
- assumed balance and horizon;
- base APY, each qualifying APY component, estimated gross interest, known annual fees, and estimated net interest;
- opening and ongoing balance requirements and material requirements such as paperless statements;
- why meaningful alternatives were lower-yielding or infeasible;
- card approval uncertainty, eligibility-maintenance conditions, variable-balance effects, and separation of spending rewards from savings interest.

For a customer wanting both products, clearly distinguish (a) the savings projection conditional on EcoCard approval and continued eligibility from (b) separate potential card rewards. For EcoCard, provide its documented online application sequence—provide identity and financial details, review terms, submit, then receive a decision or documentation request—without claiming an application has been filed when no application tool exists.

After giving the comparison, ask an unambiguous question such as: **“Would you like me to open Green Account savings?”** Record the exact affirmative selection. If the customer does not expressly choose a class, do not open any account.

### 6. Open after selection, not before
Only after all opening gates pass and the customer explicitly selects the exact class:

1. Unlock `open_bank_account_4821` as documented.
2. Call it with the authenticated `user_id`, `account_type` set to `savings`, and the exact selected official `account_class` ending in `Account` (for example, `Green Account`).
3. Report success only after a non-error result. If it fails, report the returned failure without asserting the account exists.

Do not shorten, paraphrase, or normalize the official account-class string.

### 7. Handle opening funding separately
After a successful opening, ask whether the customer authorizes an immediate transfer of the required opening deposit from a specified checking account.

- **Authorized:** Validate source and destination are distinct accounts of the customer, both are `OPEN` or `ACTIVE`, the source has sufficient available funds, and the amount is positive USD and at least the product’s opening minimum. Unlock and call `transfer_funds_between_bank_accounts_7291` only then.
- **Declined or deferred:** Do not call the transfer tool. State clearly that the new savings account must be funded within **30 days** by an internal transfer or external deposit or it will be closed. State the documented product minimum (Green: $100) and any ongoing balance requirement.
- **Transfer failure:** Do not claim the account was funded. Explain the returned reason and revalidate any newly proposed source or amount before retrying.

## Helper interface
Run `scripts/compare_net_return.py` with JSON on standard input, for example:

```json
{
  "principal": 5000,
  "horizon_days": 365,
  "candidates": [
    {
      "name": "Green Account + EcoCard",
      "base_apy_pct": 4.0,
      "card_bonus_apy_pct": 0.5,
      "checking_bonus_apy_pct": 0,
      "other_bonus_apy_pct": 0,
      "annual_fees": 50,
      "one_time_fees": 0,
      "minimum_opening_deposit": 100,
      "minimum_ongoing_balance": 500,
      "opening_requirement_met": true,
      "ongoing_requirement_met": true
    }
  ]
}
```

The script emits candidate APY components, estimated gross interest, prorated annual fees, estimated net return, feasibility, and a descending feasible ranking. Validate that every supplied number comes from documentation and that feasibility flags reflect the customer’s actual plan. A script error, missing term, or uncertain eligibility is a reason to correct facts or qualify the advice, not to invent an answer.
