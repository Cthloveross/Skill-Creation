# Product-feature normalization for checking-account recommendations

Use these normalized fields for common checking requirements. Amounts are USD; rates are percentage points unless the source says otherwise.

| Customer requirement | Field and comparison | Evidence/scope check |
|---|---|---|
| no overdraft fee | `overdraft_fee`, `equals`, `0` | The source must expressly state the account's overdraft fee. Do not use an ATM or maintenance fee. |
| minimum monthly ATM rebates | `atm_rebate_cap`, `at_least`, requested amount | Use only the documented recurring rebate cap that covers the relevant out-of-network ATM fees. Keep domestic, foreign, and operator-surcharge scope distinct. |
| maximum required balance | `minimum_balance_requirement`, `at_most`, requested maximum | Do not substitute a maintenance-fee waiver threshold for a minimum-balance requirement. |
| minimum interest yield | `apy`, `at_least`, requested percentage | Use the stated APY, not a monthly or nominal rate. |

A source that does not establish a field must leave it out of the account's facts. A fee-rebate cap is not proof that the associated fee is zero. A zero domestic ATM fee is not proof of a zero foreign ATM fee, and neither establishes a zero overdraft fee.
