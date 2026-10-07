# Rewards rules used by the audit helper

All earned rewards are whole points: calculate the applicable points-per-dollar rate against the transaction amount and floor the result.

Cash-back cards store their cash-back reward as points in the transaction system. One point represents $0.01 when redeemed as a statement credit or checking credit. EcoCard stores sustainability points and earns 5 points per dollar on qualifying green purchases and 1 point per dollar otherwise; its points also redeem at $0.01 per point.

## Card rules

| Card | Standard rule | Enhanced rule / conditions |
|---|---:|---|
| Diamond Elite Card | 5 points per dollar | Applies to eligible posted purchases. |
| Business Platinum Rewards Card | 1.5 points per dollar | 4 points per dollar for Travel, Software, and Media Advertising purchases, subject to merchant coding. |
| Business Silver Rewards Card | 1 point per dollar | 10 points per dollar for Travel and Software. Concur, SAP Concur, Expensify, Navan, Apple, Microsoft, Dell, Xbox Game Pass, PlayStation Plus, Nintendo Switch Online, Coursera, Udemy, LinkedIn Learning, Skillshare, and Pluralsight stay at the standard rate. |
| EcoCard | 1 point per dollar | 5 points per dollar on qualifying green purchases. Target, Walmart, Amazon, and ThredUp remain standard rate. EV charging receives the high rate only at Tesla Supercharger, ChargePoint, or EVgo. |

## Business Silver offer logic

The documented offer window is 2024-11-14 through 2025-11-14. An account must open within that window, and a transaction must fall in the first six calendar months after that account opening. The offer doubles the normally applicable Business Silver rate, including the standard rate for an excluded merchant. The audit helper makes the offer-window values configurable in input so a deployment can use documented program configuration without code changes.

Transactions that are not completed posted purchases, or whose eligibility cannot be established from the supplied data, are not asserted to be correct.