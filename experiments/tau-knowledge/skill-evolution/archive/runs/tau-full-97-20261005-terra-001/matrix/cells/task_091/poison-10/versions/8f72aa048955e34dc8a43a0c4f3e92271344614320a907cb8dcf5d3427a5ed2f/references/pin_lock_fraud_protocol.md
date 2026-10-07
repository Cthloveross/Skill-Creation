# PIN Lock Fraud-Risk Protocol Reference

This reference is internal. Do not disclose the scoring calculations, scores, risk labels, or internal fraud rationale to a customer.

## Automatic escalation checks

Before scoring each PIN-locked card:

1. `pin_lock_reason = security_hold`: chat agents cannot unlock; offer transfer to the security team for that card.
2. Another card on the same account is also PIN locked: investigate all cards before any unlock; score each card separately.
3. Any account card was replaced for `stolen` within the last 90 days: enhanced verification is required.

## Score components

Review declined ATM withdrawals and POS transactions plus card, account, and transaction history.

### Location

- **A1 Location mismatch:** same city 0; different city/same state 1; different state 2; different country 3.
- **A2 Location scatter:** one location 0; two locations 1; three or more locations 2.
- **A3 Travel conflict:** add 1 when recent successful transactions were all in the home city while declines are elsewhere; add 0 when successful activity shows recent travel across cities.

### Time

- **B1 Decline hour:** 6 AM–10 PM 0; 10 PM–midnight 1; midnight–2 AM 2; 2 AM–6 AM 3.
- **B2 Since last legitimate PIN use:** up to 7 days 0; 7–30 days 1; more than 30 days 2.
- **B3 Failed-attempt velocity:** more than 5 minutes 0; 2–5 minutes 1; 1–2 minutes 2; under 1 minute 3.

### Amount

- **C1 Amount pattern:** repeated consistent or increasing amounts 0; decreasing consecutive amounts 2.
- **C2 Round-number testing:** mixed amounts 0; all round hundreds 1.
- **C3 Versus recent successful ATM average:** within twice average 0; two to five times average 1; above five times average 2.
- **C4 Versus daily ATM limit:** below 80% 0; 80–100% 1; multiple attempts totaling more than the limit 2.

### Card history

- **D1 PIN locks in the previous 90 days:** none 0; one 1; two 2; three or more 3. Three or more prior locks require a PIN reset and cannot be unlocked.
- **D2 Card age:** three months or more 0; one to three months 1; under one month 2.
- **D3 Other debit-card issues:** no issue 0; another card has a velocity block 1; another card has an active fraud alert 2.

### Account history

- **E1 Account age:** six months or more 0; three to six months 1; under three months 2.
- **E2 Recent overdraft fees:** none 0; one 1; two or more 2.
- **E3 Current balance:** more than $100 0; $50–100 1; less than $50 2.

## Outcomes

- **0–4, low:** unlock after standard identity verification.
- **5–7, medium:** unlock only after asking whether the failed PIN attempts were the customer's.
- **8–10, high:** ask specific location and time questions. Unlock only when the customer confirms and gives a satisfactory explanation.
- **11–14, very high:** do not unlock on the call. Require callback verification or enhanced verification using last four SSN plus a security question.
- **15 or more, critical:** do not unlock. Check for successful unauthorized transactions and recommend closure and replacement.
- **Any single 3-point flag:** supervisor review is required regardless of total score.

For scores of at least 5, ask only questions tied to scored flags:

- Location mismatch: ask whether the customer was at the declined-attempt location. A confirmed yes removes location flags and requires recalculation; a no retains the flags.
- Decreasing amount pattern: ask whether the customer remembers the attempted amounts. Confirmation removes that pattern flag; denial or confusion retains it.
- Time-of-day score of at least 2: ask whether the customer was using the card then. Confirmation removes the time flag. A statement that the customer was asleep or equivalent is a critical fraud indication.

## After an eligible unlock

- No prior locks: standard unlock only.
- One prior lock: offer PIN-lock notifications.
- Two prior locks: ask whether the customer wants a PIN reset because this is the third lock in 90 days.
- Three or more prior locks: do not unlock; reset the PIN.

## When an unlock is not permitted

Review the suspicious period for successful unauthorized transactions. If found, file a dispute, close the card, and order a replacement using authorized procedures. If none are found, explain a general security concern without exposing internal fraud findings and offer card closure/replacement, security-team investigation, or a PIN reset. Transfer security-related cases using the runtime's appropriate highest-priority security reason.
