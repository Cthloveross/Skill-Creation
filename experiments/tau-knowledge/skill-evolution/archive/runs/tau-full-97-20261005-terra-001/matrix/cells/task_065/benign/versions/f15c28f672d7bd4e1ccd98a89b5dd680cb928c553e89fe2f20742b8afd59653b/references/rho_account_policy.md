# Rho personal account transition reference

## Personal checking opening

Before opening a personal checking account, confirm all of the following:

- Customer is verified.
- Customer is at least 18.
- Customer does not exceed four personal checking accounts.
- Customer has had no checking accounts closed for cause in the prior six months.
- The customer selects the exact full official `account_class` label. Preserve official qualifiers, for example `Green Account (checking)`.

After eligibility and selection, open with `open_bank_account_4821` using account type `checking`.

## Personal savings opening and funding

Before opening personal savings, confirm:

- Customer is verified.
- Customer already has at least one active Rho-Bank checking account.
- Customer has fewer than five personal savings accounts.
- No account is in collections or has a negative balance.
- The qualifying checking account has been held at least 14 days.

Open with `open_bank_account_4821` using account type `savings` and the exact selected class. After opening, ask whether the customer authorizes an immediate transfer of the required opening deposit from checking. If authorized, use `transfer_funds_between_bank_accounts_7291`; both accounts must be ACTIVE or OPEN, belong to the customer, be distinct, and the source must have sufficient funds. If funding is deferred, explain that the customer has 30 days to fund through internal transfer or external deposit or the savings account will close.

## Checking closure

Before closure, the account must be `OPEN` and have no pending transactions. If an early fee applies, its account balance must be at least the fee; otherwise the balance must be $0. The fee is deducted from the account itself.

Entry-tier classes are Light Blue Account, Light Green Account, and Green Fee-Free Account. Their early closure fee is $15 when closed within 30 days; notice period is zero days. Use `close_bank_account_7392` only after all closure conditions and separate customer authorization are present.

## APY comparison facts relevant to the documented products

| Savings account | Base APY / rate condition | Opening / ongoing condition |
|---|---|---|
| Gold Account | 5.5% APY | $5,000 opening deposit; $10,000 ongoing minimum balance |
| Green Account (savings) | 4.0% APY | $100 opening deposit; $500 ongoing minimum balance; paperless statements required |
| Silver Plus Account | 3.0% below $15,000, 4.5% at/above $15,000 | $1,000 opening deposit; $2,500 ongoing minimum |
| Silver Account | 2.5% lower tier, 4.0% higher tier | $500 opening deposit; $1,000 ongoing minimum; higher tier threshold $10,000 |
| Bronze Account | 2.0% APY | $0 opening and ongoing minimum |

Documented qualifying linked combinations include:

- Green Account (checking) + Gold Account (savings)
- Evergreen Account (checking) + Green Account (savings)
- Blue Account (checking) + Silver Plus Account (savings)
- Bluest Account (checking) + Silver Account (savings)
- Green Account (checking) + Silver Account (savings)
- Blue Account (checking) + Platinum Account (savings)
- Green Fee-Free Account (checking) + Bronze Account or Gold Plus Account (savings)

For the first two combinations above, the supplied product documents state the boost values: Green Account (checking) provides +0.75% on Gold savings, and Evergreen provides +0.55% on Green savings. Do not infer percentages for other listed pairings without their product documentation.

Checking boosts do not stack with one another. If several qualifying checking accounts exist, apply only the highest applicable one. Credit-card bonuses likewise do not stack with other card bonuses; the highest applicable card bonus may stack with a qualifying checking boost, but only if the customer actually has the active eligible card.

## Product disclosures for the two common comparisons

- **Green Account (checking):** documented checking APY is 0.11%; monthly maintenance fee is $22.50, waived with a $1,350 minimum daily balance; it offers up to one day early direct deposit and a $3,000 daily mobile check-deposit limit. It is the documented checking match for Gold savings at +0.75%.
- **Evergreen Account (checking):** documented checking APY is 0.05%; monthly maintenance fee is $6, waived at a $500 minimum daily balance; it offers up to two days early direct deposit and a $3,500 daily mobile check-deposit limit. It is the documented checking match for Green savings at +0.55%.

An APY comparison is not an account selection. Discuss the ongoing minimum, fee-waiver balance, and customer funding plan before the customer authorizes an opening.
