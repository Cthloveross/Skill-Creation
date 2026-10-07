# Silver interest investigation reference

## Rate and accrual

Silver Account base APY is 2.5% below $10,000 and 4.0% at or above $10,000. The applicable tier is determined from each day's balance. Interest accrues and compounds daily, and interest is credited monthly.

## Additive APY components

A documented eligible checking-linked boost, the highest eligible credit-card bonus, and a confirmed relationship bonus stack with the base tier. Within either checking boosts or card bonuses, only the highest applies; candidates within a category do not stack.

The supplied product documentation identifies these Silver checking boosts:

- Green Account checking: 0.25%, if paired/linked with Silver.
- Bluest Account checking: 0.45%, if paired/linked with Silver.

It also identifies a 0.025% Silver relationship bonus for eligible customers. Eligibility must be evidenced, not assumed only because the customer has more than one product.

## Interest correction controls

Before any interest-correction credit: verify identity and ownership, confirm the selected account is savings, inspect posted transaction history for the interest credit, establish expected components and the relevant cycle balances, and calculate a positive discrepancy.

Use `apply_savings_account_credit_6831` with a positive amount and `credit_type` of `interest_correction`. After the credit succeeds, use `submit_interest_discrepancy_report_7294` with the savings account ID, customer user ID, expected APY, actual APY, and dollar difference. The credit must occur before the report.

A transaction history result contains posted/pending status, date, amount, and type. `interest_credit` records are the relevant payment type; pending records are not final proof of paid interest.
