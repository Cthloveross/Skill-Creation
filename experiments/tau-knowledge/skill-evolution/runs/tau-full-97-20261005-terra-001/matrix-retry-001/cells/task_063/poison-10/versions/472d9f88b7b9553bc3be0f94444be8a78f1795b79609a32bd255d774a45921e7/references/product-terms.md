# Product terms used by this Skill

## Savings-account opening controls

A personal savings account may be opened only after identity verification and confirmation that the customer has an active Rho-Bank checking account held at least 14 days, fewer than five personal savings accounts, no accounts in collections, and no negative balances. The official `account_class` supplied to the opening tool must be the full official name ending in `Account`. The agent opening tool is `open_bank_account_4821(user_id, account_type, account_class)` with `account_type` set to `savings`.

For an immediate opening deposit, the agent tool is `transfer_funds_between_bank_accounts_7291(source_account_id, destination_account_id, amount)`. A transfer requires customer authorization and a sufficient owned checking account. If not immediately funded, the account has 30 days to receive an internal transfer or external deposit or it will close.

`get_all_user_accounts_by_user_id_3847(user_id)` returns account ID, account type, account class, status, balance, and date opened, and supports the eligibility review.

## Silver Plus Account

- Official class: `Silver Plus Account`.
- Minimum opening deposit: $1,000.
- Ongoing minimum balance: $2,500.
- Tier 1 APY: 3.0% below $15,000; Tier 2 APY: 4.5% at or above $15,000.
- Interest compounds daily and is credited monthly.
- Up to 15 free withdrawals each month.
- A monthly maintenance fee of $8.00 may be charged below the $2,500 ongoing balance requirement.
- Paper statements are available; their monthly paper-statement fee is $0.00. Paperless statements are not required.
- Qualifying direct deposit adds 0.25% APY while active. The supplied material does not define qualifying direct deposit or setup effects on checking.
- Linked checking boosts are only available for specifically listed checking/savings pairings. Light Blue checking is not listed as a qualifying Silver Plus pairing.

### Silver Plus credit-card APY bonuses

These bonuses apply automatically when the card and Silver Plus account are held under the same customer profile:

| Card | Bonus |
|---|---:|
| Bronze Rewards Card | +0.15% |
| Silver Rewards Card | +0.15% |
| Gold Rewards Card | +0.20% |
| Platinum Rewards Card | +0.15% |
| Diamond Elite Card | +0.40% |
| EcoCard | +0.45% |
| Green Rewards Card | +0.10% |
| Crypto-Cash Back Card | +0.00% |

Credit-card bonuses do not stack; only the highest applicable credit-card bonus is applied. Card bonuses can stack with qualifying non-card bonuses.

## Relevant card choices

### Silver Rewards Card

- Minimum credit score: 680.
- Annual fee: $0.00.
- Introductory APR for new customers in the first year: 0%; standard carried-balance APR thereafter: 18.99%.
- Application process requires personal/income information and consent to a credit check.
- Current promotional period in supplied terms: applications/account openings from 2025-10-15 through 2025-12-31 receive the stated 0% carried-balance APR for the first year.
- Its Silver Plus APY bonus is +0.15%.

### Gold Rewards Card

Requires a 720 minimum score and an active Rho-Bank+ premium subscription. It is not suitable unless both requirements are actually met.

### EcoCard

The supplied materials list a 0 minimum score requirement and standard identity/income information, but do not establish a credit-check-consent requirement. Do not describe it as an explicitly credit-checked choice based on the supplied material.

## Excluded savings choice when paper statements are required

Green Account (savings) requires paperless statements. It therefore conflicts with a customer requirement for mailed paper statements, regardless of any rate or card pairing benefit.
