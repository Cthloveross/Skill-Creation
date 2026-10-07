# PIN-lock scoring guide

Derive these values independently for each locked card from verified card data and relevant transaction history. Evaluate only the documented declined ATM/POS attempts. Do not infer absent location, time, prior-lock, or successful-PIN-use facts.

## Flags

- **A1 Location mismatch:** same city 0; different city/same state 1; different state 2; different country 3.
- **A2 Location scatter:** all same location 0; two locations 1; three or more 2.
- **A3 Travel pattern conflict:** add 1 if successful transactions in the prior seven days are all in the home city and declines are elsewhere; otherwise 0 for evidenced recent travel.
- **B1 Time of day:** 06:00–22:00 0; 22:00–00:00 1; 00:00–02:00 2; 02:00–06:00 3.
- **B2 Since last legitimate PIN use:** through seven days 0; 7–30 days 1; more than 30 days 2.
- **B3 Attempt velocity:** more than five minutes 0; two to five minutes 1; one to two minutes 2; under one minute 3.
- **C1 Amount pattern:** same amount retries or increasing amounts 0; decreasing attempts 2.
- **C2 Round-number testing:** mixed amounts 0; all round hundreds 1.
- **C3 Versus historical ATM average:** within 2x 0; 2–5x 1; more than 5x 2. Calculate the average from recent successful ATM withdrawals only when sufficient records are available.
- **C4 Versus daily ATM limit:** below 80% 0; 80–100% 1; multiple attempts totaling more than the limit 2.
- **D1 Prior PIN locks in 90 days:** none 0; one 1; two 2; three or more 3 and reset-only.
- **D2 Card age:** more than three months 0; one to three months 1; less than one month 2.
- **D3 Other card issues:** none 0; another card has a velocity block 1; another card has an active fraud alert 2.
- **E1 Account age:** more than six months 0; three to six months 1; less than three months 2.
- **E2 Overdraft history:** none 0; one overdraft fee 1; two or more 2.
- **E3 Current balance:** more than $100 0; $50–100 1; less than $50 2.

A score of 3 for any single flag always requires supervisor review. Any critical fraud response from the customer, including denying a high-risk-time attempt because they were asleep, overrides ordinary score routing.

## Thresholds

| Total | Required route |
|---:|---|
| 0–4 | Low: standard verification before unlock |
| 5–7 | Medium: ask whether failed PIN attempts were theirs |
| 8–10 | High: specific location/time confirmation and satisfactory explanation required |
| 11–14 | Very high: no chat unlock; callback or enhanced verification |
| 15+ | Critical: no unlock; investigate unauthorized successes and recommend closure/replacement if fraud suspected |
