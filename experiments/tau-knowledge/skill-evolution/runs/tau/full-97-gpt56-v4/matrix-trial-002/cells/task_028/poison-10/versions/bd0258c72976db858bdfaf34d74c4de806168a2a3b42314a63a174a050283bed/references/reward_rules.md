# Reward-review rules

## Stored rewards and cash value

All listed cash-back cards, including Crypto-Cash Back, store rewards as points because of a legacy system representation. For these cards, 1 point redeems as $0.01 of cash back when used as a statement credit or credited to a Rho-Bank checking account. The stored point value is therefore not a separate loyalty currency.

EcoCard is the exception: it earns sustainability points. Its points also redeem at $0.01 each, but its earning rule is 5 points per dollar on Green purchases and 1 point per dollar otherwise. Do not apply a cash-back percentage calculation to EcoCard.

## Rounding

For every credit-card reward calculation, fractional points are truncated down to the nearest whole point for each purchase. Never round to nearest and never pool fractional points from multiple transactions.

Given a dollar transaction amount and a cash-back percentage expressed as a percentage numeral, expected cash-back points are:

`floor(amount_in_dollars * percentage_numeral)`

Thus a 2.0% rate produces 2 points per eligible dollar before truncation.

## Crypto-Cash Back

- Earn rate: 2.0% on eligible purchases.
- Virtual-card use does not prevent earning rewards.
- Crypto redemption minimum: $30 in rewards.
- Crypto conversion fee: 1.25% of the amount converted. This fee applies at redemption and must not be deducted from transaction rewards when auditing earn rates.

## Known eligible transaction categories

Travel, Software, Media, Green (also called Sustainable), Operations, Transportation, Groceries, Dining, Entertainment, Utilities, and Shopping are valid reward categories. `Other` denotes card-specific exclusions or exceptions. A category not in the known list is not sufficient evidence to calculate a supported expected reward; flag it as indeterminate rather than assume a rate.

## Dispute route

For a cash-back discrepancy, the customer must initiate the available tool with their own user ID and the specific transaction ID:

`submit_cash_back_dispute_0589(user_id: str, transaction_id: str)`

The agent should verify the transaction ID before providing the tool and should not collect card-number details.
