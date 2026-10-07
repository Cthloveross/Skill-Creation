# Product facts for savings/card yield comparisons

Use these facts only where their stated conditions are met. APY bonuses are additive percentage points. The general policy permits only the highest applicable credit-card bonus, not a sum of card bonuses.

## Gold Account and relevant cards

- Gold Account base APY: 5.5%. Its standard minimum balance is $10,000. Interest compounds daily and is credited monthly.
- Gold Rewards Card on Gold Account: +0.025% APY and reduces the Gold Account minimum balance from $10,000 to $5,000 while the card is active and associated. Gold Rewards Card application requires a minimum credit score of 720 and an active Rho-Bank+ premium subscription. Its annual fee is $0.
- EcoCard on Gold Account: +0.6% APY. It does **not** receive the Gold Rewards Card's reduced-balance benefit. EcoCard has no minimum credit-score requirement, requires identity and income information, and has a $50 annual fee.
- If a narrative example states a total inconsistent with 5.5% plus 0.025%, calculate the disclosed additive values: 5.525%, not an unsupported rounded or altered rate.

## Other documented alternatives for an $8,000-scale balance

- Silver Account: balances below its $10,000 higher-APY threshold use a 2.5% lower-tier APY. EcoCard provides +2.2% on Silver. Silver's minimum opening deposit is $500 and ongoing minimum balance is $1,000.
- Green Account (savings): base APY 4.0%, ongoing minimum balance $500, and EcoCard bonus +0.5%.
- Gold Plus requires a $10,000 opening deposit.
- Platinum requires a $50,000 ongoing balance.
- Platinum Plus requires a $50,000 opening deposit and $100,000 ongoing balance.

## Linked checking and stack rules

- A checking boost applies only to listed checking/savings pairings. Light Blue checking is not a listed qualifying pairing for a Gold Account boost.
- A qualifying checking boost may stack with the selected credit-card bonus, but multiple checking boosts do not stack; use only the highest applicable one.
- Credit-card bonuses do not stack. Choose the highest applicable card bonus for the selected savings account.

## Savings-account opening prerequisites and procedure

Before opening a personal savings account, confirm: identity is verified; the customer has an active Rho-Bank checking account; checking tenure is at least 14 days; the customer has fewer than five personal savings accounts; and the customer has no collections accounts or negative balances. Do not open if any condition fails.

After the customer confirms the exact full account class name and authorization, the documented internal action is `open_bank_account_4821(user_id, account_type, account_class)`, using `account_type` `savings` and an official class ending in `Account`. Ask whether the customer wants an immediate opening-deposit transfer. Only with authorization, use `transfer_funds_between_bank_accounts_7291(source_account_id, destination_account_id, amount)`. If funding is deferred, communicate the 30-day funding window and closure consequence.

## Source basis

These facts are derived from the packaged Gold, Silver, Green, Gold Plus, Platinum, Platinum Plus, credit-card, linked-account, and savings-opening policy documents. They do not establish an individual customer's approval, verification, subscription status, checking tenure, or account standing.
