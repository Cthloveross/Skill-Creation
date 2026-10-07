# ATM policy reference for reconciliation

Use only for the listed checking-account products. Rho-Bank fees and third-party ATM operator surcharges are separate unless specifically described as an operator-fee rebate.

## Purple Account

- Domestic out-of-network cash withdrawal fee: $2.50 per withdrawal.
- Foreign ATM withdrawal fee charged by Rho-Bank: $0.00.
- Eligible ATM operator fees may be rebated after they post, up to a total of $30 per month.
- When reviewing a missing rebate, confirm the charge was coded as an ATM operator fee, the charge is eligible, and all posted rebates during the month. Amounts beyond the $30 monthly cap are not rebated.

## Light Blue Account

- Domestic out-of-network withdrawals: two free withdrawals per month; each additional withdrawal is $2.50.
- Foreign ATM cash withdrawals: two free withdrawals per month; each additional withdrawal is $4.00.
- Free allowances are per withdrawal, monthly, and do not roll over.
- Operator surcharges are separate.

## Dark Green Account

- Domestic out-of-network ATM withdrawal fee: 1% of the withdrawal amount, with a $1.50 minimum.
- Foreign ATM withdrawal fee: 2.5% of the withdrawal amount, with a $6.00 maximum per transaction.
- Third-party operator fees may be additional.

## Evergreen Account

- Domestic out-of-network ATM withdrawal fee: 1% of the withdrawal amount, capped at $2.50 per withdrawal.
- Foreign ATM withdrawal fee: 2% of the withdrawal amount, with a $3.00 minimum per transaction.
- Third-party operator fees may be additional.

## Credit authorization safeguards

A checking-account credit is authorized only for a confirmed fee mischarge or a missing eligible rebate. It must be the exact positive amount, use `fee_refund` or `rebate_credit`, and be made no more than once per checking account in the customer interaction. Credits cannot be made to savings or other account types, and the credit tool enforces a 14-day cooldown on the same account.
