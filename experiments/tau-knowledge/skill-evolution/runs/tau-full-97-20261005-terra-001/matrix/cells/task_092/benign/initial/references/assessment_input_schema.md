# Assessment input schema

`scripts/pin_lock_assess.py` accepts a normalized JSON object. Dates may be ISO-8601 timestamps, `YYYY-MM-DD`, or `MM/DD/YYYY`; timestamps are required where time-of-day or velocity is assessed. Amounts may be signed or unsigned; the assessment uses their absolute value.

```json
{
  "now": "timestamp",
  "target_card_id": "string",
  "customer": {
    "home_city": "string",
    "home_state": "string",
    "home_country": "string, optional; defaults to US only when omitted"
  },
  "account": {
    "account_id": "string, optional",
    "date_opened": "date",
    "balance": 0
  },
  "target_card": {
    "card_id": "string",
    "user_id": "string, optional",
    "pin_locked": true,
    "pin_lock_reason": "string or null",
    "date_issued": "date",
    "daily_atm_limit": 0,
    "prior_pin_lock_dates": ["date or timestamp"],
    "prior_pin_lock_count_90d": 0
  },
  "cards": [
    {
      "card_id": "string",
      "pin_locked": false,
      "issue_reason": "string",
      "date_issued": "date",
      "status": "ACTIVE|PENDING|FROZEN|CLOSED",
      "velocity_blocked": false,
      "fraud_alert_active": false
    }
  ],
  "declined_attempts": [
    {
      "timestamp": "timestamp",
      "amount": 0,
      "location": {"city": "string", "state": "string", "country": "string"},
      "type": "atm_withdrawal_declined|pos_declined"
    }
  ],
  "successful_transactions": [
    {
      "timestamp": "timestamp",
      "amount": 0,
      "type": "atm_withdrawal|debit_card_purchase|other",
      "pin_used": true,
      "location": {"city": "string", "state": "string", "country": "string"}
    }
  ],
  "transactions": [
    {"timestamp": "timestamp or date", "type": "overdraft_fee|other", "amount": 0, "status": "posted|pending"}
  ],
  "customer_confirmations": {
    "location": "confirmed|denied|unknown",
    "amount_pattern": "confirmed|denied|unknown",
    "time_of_day": "confirmed|denied|unknown|asleep"
  },
  "satisfactory_explanation": false
}
```

`prior_pin_lock_count_90d` is preferred when the source provides it. Otherwise provide `prior_pin_lock_dates`; the script counts dates in the prior 90 days and excludes future dates. Do not include the current lock as a prior lock.

A complete assessment normally needs all declared sections, at least one declined attempt with timestamp/amount/location, an account date/balance, card issue date/ATM limit/lock history, all account cards, successful PIN-use history, successful ATM history, and transaction history. If a source does not expose a needed fact, omit it rather than fabricating it. The script will identify the missing input and prevent a complete assessment.

Locations must be normalized before calling the script. A location is distinct when its normalized city, state, or country differs. The executor must parse raw transaction descriptions only when the location can be determined reliably; otherwise leave it unknown.
