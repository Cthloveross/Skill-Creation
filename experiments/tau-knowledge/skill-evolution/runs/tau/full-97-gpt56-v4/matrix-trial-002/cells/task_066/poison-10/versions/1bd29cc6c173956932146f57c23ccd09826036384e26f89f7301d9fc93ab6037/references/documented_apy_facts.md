# Documented APY comparison facts

Use these records only for a product comparison. They do not prove that any particular customer owns, qualifies for, has been approved for, or has linked a product.

## Global selection rules

- Multiple card APY bonuses do not stack: only the highest applicable card bonus applies.
- Multiple checking APY boosts do not stack: only the highest applicable checking boost applies.
- The selected card and checking amounts may stack with each other.
- Relationship bonuses may stack only if their separate qualification is established.

## Savings accounts and rates

| Savings account | Base/tier APY | Ongoing minimum balance | Relevant card bonuses |
|---|---:|---:|---|
| Gold Account | 5.5% | $10,000 | EcoCard +0.6%; Gold Rewards Card +0.025%; other documented values may apply |
| Silver Account | 2.5% below $10,000; 4.0% at or above $10,000 | $1,000 | EcoCard +2.2%; Gold Rewards Card +0.5%; Crypto-Cash Back Card +0.5%; Silver Rewards Card +0.1% |
| Green Account (savings) | 4.0% | $500 | Diamond Elite Card +0.6%; EcoCard +0.5%; Silver Rewards Card +0.45%; Green Rewards Card +0.4%; Platinum Rewards Card +0.35% |
| Silver Plus Account | 3.0% below $15,000; 4.5% at or above $15,000 | $2,500 | EcoCard +0.45%; Diamond Elite Card +0.4%; Gold Rewards Card +0.2% |
| Gold Plus Account | 6.0% | $25,000 | Gold Rewards Card +0.35%; Crypto-Cash Back Card +0.3%; Diamond Elite Card +0.25% |
| Platinum Account | 6.5% | $50,000 | Diamond Elite Card +0.35%; Platinum Rewards Card +0.25%; Gold Rewards Card +0.15% |
| Platinum Plus Account | 7.0% | $100,000 | Diamond Elite Card +0.6%; Platinum Rewards Card +0.4%; Crypto-Cash Back Card +0.25% |
| Diamond Elite Account | 7.5% | $250,000 | Diamond Elite Card +0.5%; Crypto-Cash Back Card +0.15% |

The Silver Account has a documented 0.025% relationship bonus for eligible customers. It is not automatic from the supplied facts.

The Gold Rewards Card material describes a 0.025% Gold Account benefit both in a card-bonus listing and as a relationship bonus. Do not count it twice.

## Documented linked-checking boosts

| Checking account | Eligible savings account | Boost |
|---|---|---:|
| Green Account (checking) | Gold Account | +0.75% |
| Bluest Account | Silver Account | +0.45% |
| Evergreen Account | Green Account (savings) | +0.55% |

Other pairings may be listed as eligible without a numerical boost in the supplied product material. Do not substitute a number when none is documented.

## Known card-application caveats

- EcoCard states no credit-score requirement, but requires standard identity and income information and remains subject to approval.
- Gold Rewards Card requires a 720 minimum credit score and an active premium subscription, in addition to underwriting/application requirements.
- The supplied material does not establish application eligibility for every other card. Do not represent those cards as obtainable without verification.

## Example calculator input for a documented $6,000 comparison

This is a product catalog example, not a customer record or authorization:

```json
{
  "balance": 6000,
  "savings_accounts": [
    {"id":"silver","name":"Silver Account","minimum_balance":1000,
     "tiers":[{"minimum_balance":0,"apy":2.5},{"minimum_balance":10000,"apy":4.0}]},
    {"id":"green","name":"Green Account (savings)","minimum_balance":500,"base_apy":4.0},
    {"id":"gold","name":"Gold Account","minimum_balance":10000,"base_apy":5.5}
  ],
  "checking_boosts": [
    {"savings_id":"silver","checking_name":"Bluest Account","apy":0.45},
    {"savings_id":"green","checking_name":"Evergreen Account","apy":0.55},
    {"savings_id":"gold","checking_name":"Green Account (checking)","apy":0.75}
  ],
  "card_bonuses": [
    {"savings_id":"silver","card_name":"EcoCard","apy":2.2,"eligibility_note":"application approval required"},
    {"savings_id":"green","card_name":"EcoCard","apy":0.5,"eligibility_note":"application approval required"},
    {"savings_id":"green","card_name":"Diamond Elite Card","apy":0.6,"eligibility_note":"application eligibility not established in supplied facts"},
    {"savings_id":"gold","card_name":"EcoCard","apy":0.6,"eligibility_note":"application approval required"}
  ]
}
```

At that balance, Gold is excluded by its $10,000 ongoing minimum. Silver plus Bluest plus EcoCard totals 5.15% (2.5 + 0.45 + 2.2), conditional on all products being approved and linked. Green plus Evergreen plus EcoCard totals 5.05%; it reaches 5.15% with Diamond Elite Card, but its application eligibility is not established here.
