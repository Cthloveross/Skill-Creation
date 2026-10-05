# PIN-lock fraud-risk assessment reference

Use this reference only when a card lookup shows `pin_locked = TRUE`. Do not reveal the scoring model or calculations to the customer. Inspect all cards on the account and relevant transaction history before deciding anything.

## Automatic escalation checks

Before scoring, check all of the following:

1. `pin_lock_reason = security_hold`: chat agents cannot unlock; offer security-team transfer.
2. Another card on the same account is also PIN locked: finish investigation of every card before any unlock; score each card independently.
3. A card on the account was replaced for `stolen` within 90 days: require enhanced verification.

## Score the flags

Review declined `atm_withdrawal_declined` or `pos_declined` history, successful recent history, card data, current account data, customer address city, and the linked account. Add each applicable score.

### A. Location

- **A1 Location mismatch:** same city 0; different city in same state 1; different state 2; different country 3 (critical).
- **A2 Location scatter:** one location 0; two locations 1; three or more 2.
- **A3 Travel conflict:** add 1 if successful transactions in the last 7 days are all in the home city but declines are elsewhere; add 0 if successful activity supports travel across cities.

### B. Time

- **B1 Time of day:** 06:00–22:00 0; 22:00–00:00 1; 00:00–02:00 2; 02:00–06:00 3.
- **B2 Since last legitimate PIN use:** under 24 hours 0; 1–7 days 0; 7–30 days 1; over 30 days 2.
- **B3 Failed-attempt velocity:** over 5 minutes apart 0; 2–5 minutes 1; 1–2 minutes 2; under 1 minute 3.

### C. Amount

- **C1 Pattern:** same/retried or increasing amounts 0; decreasing consecutive amounts 2.
- **C2 Round-number testing:** mixed amounts 0; all round hundreds 1.
- **C3 Versus average successful ATM withdrawal:** within 2x 0; 2–5x 1; more than 5x 2.
- **C4 Versus daily ATM limit:** below 80% 0; 80–100% 1; multiple attempts totaling over the daily limit 2.

### D. Card history

- **D1 PIN locks in the last 90 days:** 0 prior 0; 1 prior 1; 2 prior 2; 3 or more 3. Three or more requires a PIN reset, not an unlock.
- **D2 Card age:** 3 months or more 0; 1–3 months 1; less than 1 month 2.
- **D3 Other-card issues:** none 0; another card velocity-blocked 1; another card has active fraud alert 2.

### E. Account

- **E1 Account age:** more than 2 years 0; 1–2 years 0; 6–12 months 0; 3–6 months 1; less than 3 months 2.
- **E2 Recent overdraft fees:** none 0; one 1; two or more 2.
- **E3 Current balance:** more than $500 0; $100–500 0; $50–100 1; under $50 2.

Any individual 3-point flag requires supervisor review regardless of the total.

## Required outcome by total

- **0–4, low:** unlock only after standard identity verification.
- **5–7, medium:** additionally ask, “I see failed PIN attempts on your card. Were those attempts yours?” Unlock only after an appropriate response.
- **8–10, high:** ask location/time-specific questions and unlock only if the customer confirms and provides a satisfactory explanation.
- **11–14, very high:** do not unlock on this interaction; require callback verification or enhanced verification (last four SSN plus security question).
- **15+, critical:** never unlock. Check for successful unauthorized transactions, recommend card closure/replacement, and follow dispute/security procedures as appropriate.

For a score of 5+, ask questions tied to actual scored flags. A confirmed location can remove the location flag and require recalculation. A confirmed decreasing amount pattern can remove that pattern flag. If the customer says they were asleep or otherwise denies an attempt that produced a 2+ point time flag, treat it as a critical fraud indicator rather than clearing that flag.

## After an eligible unlock

- Zero prior locks: standard unlock.
- One prior lock: offer PIN-lock notifications.
- Two prior locks: offer PIN reset because this is the third lock in 90 days.
- Three or more prior locks: reset PIN; do not unlock.

If unlocking is not allowed, look for successful unauthorized transactions during the suspicious period. If found, follow dispute, card-closure, and replacement procedures. If none are found, explain only the general security concern and offer the permitted options: PIN reset, replacement if appropriate, or security-team investigation.
