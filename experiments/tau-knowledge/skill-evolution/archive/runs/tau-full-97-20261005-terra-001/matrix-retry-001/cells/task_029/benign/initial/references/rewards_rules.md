# Rewards audit policy reference

## Reward representation

Transaction-database rewards are stored as points. For Business Platinum Rewards Card, Silver Rewards Card, and Crypto-Cash Back, they represent cash back: 1 point equals $0.01 when redeemed as a statement credit or checking-account credit. EcoCard earns sustainability points, which also redeem at $0.01 per point.

The audit helper compares whole stored points. It calculates `purchase amount × rate` and truncates any fractional point for a transaction. Use the transaction’s recorded merchant category and posted/net status; the merchant’s submitted classification controls category eligibility.

## Documented rates

| Card | Enhanced/standard rate |
|---|---|
| Business Platinum Rewards Card | 4.0% on Travel, Software, and Media/advertising; 1.5% on other purchases |
| Silver Rewards Card | 4.0% on Travel and Software; 1.0% on purchases outside those top categories |
| Crypto-Cash Back | 2.0% on eligible purchases |
| EcoCard | 5 points per dollar for qualifying Green purchases; 1 point per dollar otherwise |

Business Platinum media includes properly coded digital advertising and media buys. Agency, consulting, production, PR, talent, sponsorship, and non-media-intermediary charges may not be eligible if their merchant category is not Media. Travel and software eligibility likewise depends on the submitted category.

For EcoCard, Target, Walmart, Amazon, and ThredUp receive the standard one-point rate even when the item is eco-friendly. EV charging earns the high rate only at Tesla Supercharger, ChargePoint, or EVgo. Green/Sustainable category records may be used as evidence of qualification, but ambiguous merchant coding, marketplace processing, mixed carts, and unconfirmed charging networks require review.

## Net-purchase and timing rules

Rewards are calculated on net purchases after returns or credits, and final amounts are determined after posting. Cash equivalents, balance transfers, and fees do not earn cash back. A transaction that is pending, refunded, reversed, or otherwise not a completed/posted purchase should not be evaluated as a final standalone earnings record without reviewing its linked purchase or credit.

## Customer dispute route

For a cash-back discrepancy, the customer—not the agent—uses:

`submit_cash_back_dispute_0589(user_id: str, transaction_id: str)`

Confirm the selected transaction ID and pass this tool to the customer using the normal discoverable-user-tool mechanism. Supporting category or promotion context may be requested during review. Do not collect sensitive card details.