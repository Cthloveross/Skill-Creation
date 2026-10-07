# PIN-lock fraud-risk assessment reference

Use this reference only when a card lookup shows `pin_locked = TRUE`. Do not disclose the scoring model, individual scores, or internal fraud rationale to the customer.

## Automatic escalation checks

Before scoring, determine whether any of these applies:

1. `pin_lock_reason = security_hold`: chat cannot unlock; transfer/offer transfer to security.
2. Another card on the same account is PIN locked: investigate every card before any unlock, scoring each independently.
3. A card on the account was replaced for `stolen` within 90 days: enhanced verification is required.

## Risk factors

Use declined `atm_withdrawal_declined`/`pos_declined` history, successful recent activity, card/account data, customer home city, and the linked account.

- **Location:** mismatch: same city 0, different city/same state 1, different state 2, different country 3; scatter across two locations 1 or three-plus 2; add 1 for travel conflict when successful activity is all home-city but declines are elsewhere.
- **Time:** 06:00–22:00 0, 22:00–00:00 1, 00:00–02:00 2, 02:00–06:00 3; last legitimate PIN use 7–30 days ago 1 or more than 30 days 2; failed-attempt spacing 2–5 minutes 1, 1–2 minutes 2, under one minute 3.
- **Amount:** decreasing consecutive attempts 2; all round hundreds 1; attempt versus average successful ATM withdrawal: 2–5x is 1, over 5x is 2; 80–100% of daily limit is 1 and multiple attempts over the limit is 2.
- **Card history:** prior PIN locks in 90 days: one 1, two 2, three-plus 3; active card age one to three months 1 or under one month 2; another card velocity-blocked 1 or fraud-alerted 2.
- **Account:** account age three to six months 1 or under three months 2; one recent overdraft fee 1 or two-plus 2; balance $50–$100 is 1 or under $50 is 2.

Any single three-point factor requires supervisor review regardless of the total. Three or more prior PIN locks requires PIN reset rather than unlock.

## Outcomes

- **0–4:** standard identity verification before unlock.
- **5–7:** ask whether failed PIN attempts were the customer's; unlock only after an appropriate response.
- **8–10:** ask location/time-specific questions and unlock only after confirmation and a satisfactory explanation.
- **11–14:** do not unlock in this interaction; require callback or enhanced verification (last four SSN plus security question).
- **15+:** never unlock; check for successful unauthorized activity and follow card closure/replacement/dispute or security procedures as appropriate.

For scores of 5+, ask only questions tied to actual scored flags. If the customer denies an attempt associated with a two-plus-point time flag, treat that as a critical fraud indicator. Where an unlock is allowed, follow the applicable card-control procedure and post-unlock notification/reset requirement. If an unlock is not allowed, explain only a general security concern and offer the permitted next step.
