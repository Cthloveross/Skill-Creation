# Risk-calculator input and output schema

`scripts/score_pin_lock_risk.py` receives one UTF-8 JSON object on standard input and emits one JSON object. Omit unknown values rather than using zero, empty fake locations, or invented dates.

## Input

Required for meaningful scoring:

- `now`: ISO-8601 timestamp, preferably with timezone.
- `home_location`: object with `city`; include `state` and `country` when known.
- `declines`: chronological or unordered array of declined PIN-related attempts. Each item may contain `timestamp` (ISO timestamp), `amount` (positive number), and `location` (`city`, `state`, `country`).

Optional evidence:

- `successful_transactions`: objects with `timestamp`, `location`, `amount`, `type`, and/or `pin_success`. Include the last seven days when evaluating travel conflict and successful ATM withdrawals for historical average.
- `last_legitimate_pin_use`: ISO timestamp.
- `daily_atm_limit`: positive number.
- `prior_locks_90d`: nonnegative integer.
- `card_date_issued`, `account_date_opened`: ISO date/timestamp.
- `other_cards`: array of objects with booleans `pin_locked`, `velocity_blocked`, `fraud_alert_active`, plus optional `is_current_card`.
- `recent_stolen_replacement`: boolean, or `cards` array whose entries contain `issue_reason` and `date_issued`; the script determines whether a stolen issue falls within 90 days.
- `pin_lock_reason`: string, for example `security_hold`.
- `overdraft_count`: nonnegative integer.
- `current_balance`: numeric account balance.
- `confirmations`: object with optional booleans: `location_confirmed`, `amount_pattern_confirmed`, `time_confirmed`, `customer_was_asleep`. Confirmation removes flags only as the protocol permits; `customer_was_asleep` makes the result critical.

Locations must be normalized by the investigator where possible (e.g., state abbreviations consistently). Amounts are positive attempted withdrawal amounts. `successful_transactions` should contain actual tool/customer evidence, not assumed history.

## Output

- `flags`: internal list of flag IDs, points, reason, and removal state.
- `total_score`: total after permitted confirmations.
- `single_three_point_flag`: whether any retained flag is worth three points.
- `automatic_triggers`: known automatic triggers.
- `missing_inputs`: facts that were needed but unavailable; absence is not scored as zero.
- `protocol`: preliminary risk band and operational constraints.
- `assumptions`: deterministic aggregation choices used by the calculator.

The result is an internal working record, not customer-facing content.
