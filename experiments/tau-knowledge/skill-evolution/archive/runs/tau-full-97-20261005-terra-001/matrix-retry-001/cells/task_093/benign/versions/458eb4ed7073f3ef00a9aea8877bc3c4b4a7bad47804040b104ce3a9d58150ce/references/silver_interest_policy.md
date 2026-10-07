# Silver interest investigation reference

## Calculation

Silver Account's daily tier rate is 2.5% below $10,000 and 4.0% at or above $10,000. Interest compounds daily and is paid monthly. Each day's balance determines that day's tier.

Use only evidenced additive components. A qualifying linked checking boost may apply, as may the highest applicable active credit-card bonus and a confirmed relationship bonus. Checking boosts do not stack with each other, and card bonuses do not stack with each other.

Documented Silver checking boosts include Green Account at 0.25% and Bluest Account at 0.45%, each only for an eligible linked pairing. The Silver relationship bonus is 0.025% when eligible.

## Controls

Before an interest correction, verify identity and ownership; confirm the selected account is savings; inspect the posted interest credit; establish the cycle's complete daily balances; and calculate a positive expected-versus-actual difference. Apply `interest_correction` through `apply_savings_account_credit_6831` first. Only after that credit succeeds, submit `submit_interest_discrepancy_report_7294`.

Do not correct or report when daily balance evidence, relevant-cycle information, linkage, or applicable APY components remain unconfirmed.

## Transfer

When a customer requests human help obtaining ordinary account records after this evidence gap is explained, use `transfer_to_human_agents` with reason `other`, not `specialized_department_required`. The summary must identify known account and interest-payment facts, missing daily balances, unconfirmed linkage, and the absence of correction/report action.
