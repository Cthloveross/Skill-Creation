# EcoCard audit policy reference

This reference records only the supplied published rules used by the Skill.

## Rewards and representation

- EcoCard earns 5 sustainability points per dollar on qualifying green merchants/categories and 1 sustainability point per dollar on other purchases.
- EcoCard is the points-based product. Its sustainability points can be redeemed at $0.01 per point as a statement credit or checking-account credit.
- Transaction-database rewards are integer points. For audit arithmetic, use the posted system convention of truncating fractional points rather than rounding up.

## Green eligibility

Green purchases generally include public transportation, qualifying EV charging, renewable-energy subscriptions/providers, certified sustainable retailers and eco-labeled products, and bike-share/micromobility services. A certified partner is recognized automatically, but a current or generic category label is not proof that a particular historical transaction qualified. Seller of record, marketplace processing, mixed carts, item-level merchant data, and the historical directory can matter.

The expressly qualifying EV charging networks are Tesla Supercharger, ChargePoint, and EVgo. Other EV charging networks receive the standard rate.

## Mandatory exclusions

Target, Walmart, Amazon, and ThredUp earn the standard 1-point-per-dollar rate. The exclusion applies to all channels, eco-labeled products, and, for Amazon, marketplace orders processed by Amazon.

## Green Account-related bonus

An EcoCard can provide an additional 2.0% cashback bonus at eco-certified merchants only while the card is linked to a Green Account (savings) and is in good standing. Closing or unlinking the card removes the bonus. An account list may establish that an account exists, but does not alone establish historical linkage or good standing; request historical records or escalate when those facts cannot be retrieved.

## Account lookup constraint

The documented account lookup requires a user ID and provides account ID, type, class, status, balance, and date opened. Use it only when that exact tool is available in the runtime. It is not a substitute for unavailable linkage or historical merchant records.
