# Supported ATM fee and rebate rules

Use these rules only after identifying the actual checking account class and the transaction facts.

## Purple Account

- A domestic out-of-network ATM cash withdrawal has a $2.50 Rho-Bank fee per withdrawal.
- A foreign ATM withdrawal has no Rho-Bank ATM withdrawal fee.
- ATM-owner/operator surcharges are separate from the Rho-Bank fee.
- Eligible ATM operator fees may be rebated after they post, up to a total of $30 per calendar month. Confirm fee coding and posted rebate credits before deciding a rebate is missing.

## Light Blue Account

- Two out-of-network ATM withdrawals per month are free.
- Each additional out-of-network ATM withdrawal in that month costs $2.50.
- ATM-owner/operator surcharges are separate.

## Dark Green Account

- Domestic out-of-network ATM withdrawal fee: 1% of the cash amount, with a $1.50 minimum.
- Foreign ATM withdrawal fee: 2.5% of the cash amount, capped at $6.00 per transaction.
- Third-party operator fees are separate.

## Evergreen Account

- Domestic out-of-network ATM withdrawal fee: 1% of the cash amount, capped at $2.50 per transaction.
- Foreign ATM withdrawal fee: 2% of the cash amount, with a $3.00 minimum per transaction.
- Third-party operator fees are separate.

## Correction authority

A checking-account credit is authorized only for a documented fee mischarge or missing qualifying rebate. Confirm history, calculate the exact net correction, and use one credit call per checking account in the interaction. Use `fee_refund` for fee corrections and `rebate_credit` for missing rebates; if both are combined, use the type that applies to the majority of correction items.
