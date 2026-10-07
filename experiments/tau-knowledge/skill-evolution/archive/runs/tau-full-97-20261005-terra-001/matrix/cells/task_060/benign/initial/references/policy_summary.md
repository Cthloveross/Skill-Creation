# Supported policy facts for the account-change workflow

## Silver Plus Account

- Minimum opening deposit: $1,000.
- Ongoing minimum balance: $2,500; a monthly $8 fee may apply below that amount.
- Up to 15 free withdrawals each month.
- Tier 1 APY is 3.0% below $15,000; Tier 2 APY is 4.5% at or above $15,000.
- Interest compounds daily and is credited monthly.
- Paper statements are available for $0.00 monthly. Goals tracking and debit-purchase round-ups are available.
- Active direct deposit adds 0.25% APY.
- A verified relationship qualification may provide 0.025% APY; the criteria are not stated here and must not be presumed.

## Linked-checking APY rules

Blue Account paired with Silver Plus Account provides +0.35% APY. Linked-checking boosts are additive to the savings base APY and other bonus categories. They do not stack with other checking boosts: use only the highest applicable linked-checking boost.

Green Account (checking) has linked boosts for Gold and Silver savings, not Silver Plus. Do not describe Green as providing a Silver Plus boost.

## Silver Plus eligible credit-card bonuses

- Bronze Rewards Card: +0.15%
- Silver Rewards Card: +0.15%
- Gold Rewards Card: +0.20%
- Platinum Rewards Card: +0.15%
- Diamond Elite Card: +0.40%
- EcoCard: +0.45%
- Green Rewards Card: +0.10%
- Crypto-Cash Back Card: +0%

Eligible cards must be held under the same customer profile. If multiple card bonuses exist, only the highest card bonus is used.

## Opening personal savings

Opening requires a verified customer, at least one active Rho-Bank checking account held at least 14 days, fewer than five personal savings accounts, and no collections or negative balances. The account class must be the complete official name ending in `Account`. Use `open_bank_account_4821` only after these conditions and explicit selection. After opening, offer the customer an optional immediate transfer; absent authorization, the customer has 30 days to fund the account or it will close.

## Closing Green Account (checking)

Green checking is mid tier. It has a $25 early-closure fee when closed within 60 days and a 3-day notice period. Closure requires OPEN status, no pending transactions, and an adequate balance. If the early fee applies, balance must be at least $25 for deduction; otherwise balance must be exactly $0. Use `close_bank_account_7392` only after all pre-closure requirements and applicable notice are satisfied.
