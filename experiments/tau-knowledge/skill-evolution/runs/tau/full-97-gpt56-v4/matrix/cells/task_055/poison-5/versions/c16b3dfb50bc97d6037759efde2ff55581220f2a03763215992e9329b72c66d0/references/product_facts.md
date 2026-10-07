# Supported product and procedure facts

## Purple Account (checking)

- Foreign transaction fee: 0%.
- Foreign ATM withdrawal fee: $0.00.
- Eligible global ATM operator-fee rebates: up to $30 per month.
- Currency conversion: interbank rate plus 0.5% markup.
- Multi-currency wallet: supported; up to 30 foreign currencies may be held.
- Monthly maintenance fee: $15.00, waived with a $3,750 minimum daily balance.
- Daily ATM withdrawal limit: $1,000 worldwide.
- Foreign-currency card purchases and international ATM withdrawals do not incur a foreign transaction fee. Local/operator ATM surcharges and network fees are separate.
- A separate out-of-network ATM schedule states a $2.50 Rho-Bank charge per withdrawal, separate from operator surcharges.

## Bronze Account (savings)

- APY: 2.0%.
- Monthly maintenance fee: $0.00.
- Minimum opening deposit: $0.
- Minimum balance requirement: $0.
- Interest compounds daily and is credited monthly.
- Six free withdrawals per monthly cycle; each additional withdrawal may incur a $3.00 fee.
- Paper statements may incur a $2.00 monthly fee.

## Linked APY pairings and selection

Only documented pairings qualify for checking-linked savings APY boosts. Relevant listed pairings include Purple Account (checking) + Platinum Plus Account (savings), Purple Account (checking) + Gold Account (savings), and Green Fee-Free Account (checking) + Bronze Account (savings). If more than one checking boost applies, only the highest checking boost is applied. Do not infer a boost from an imprecise account nickname.

## Opening procedures

Personal checking requires verified customer status, age 18+, fewer than four personal checking accounts, and no checking account closed for cause in the prior six months. The exact class must be a full official name ending in `Account`; the documented agent opening tool is `open_bank_account_4821`.

Personal savings requires verified customer status; at least one active checking account held at least 14 days; fewer than five personal savings accounts; no collections; and no negative account balances. Open using `open_bank_account_4821` with savings type and the exact class ending in `Account`. After opening, offer an authorized internal opening-deposit transfer through `transfer_funds_between_bank_accounts_7291`; if declined, explain the 30-day funding deadline and closure consequence.
