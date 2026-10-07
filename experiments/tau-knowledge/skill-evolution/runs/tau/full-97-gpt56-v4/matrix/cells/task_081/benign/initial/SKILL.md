---
name: stolen-wallet-security-transfer
version: 1.0.0
description: Handle a customer reporting a stolen wallet containing bank cards who requests a human agent. Use this to prioritize urgent security escalation and select the correct transfer reason without performing unapproved card actions.
---

# Stolen Wallet Security Transfer

## When this Skill applies
Use this Skill when a customer reports that a wallet, debit card, credit card, or multiple cards were stolen or may be compromised, particularly when they ask to be transferred to a human agent.

This is a security-sensitive issue. A requested human transfer for a wallet theft is not merely a preference for human service: it is a specific fraud/security scenario.

## Required outcome
If a transfer is requested in connection with wallet theft, suspected compromise, lost/stolen cards, or potential unauthorized use, call `transfer_to_human_agents` with:

- `reason`: `fraud_or_security_concern`
- `summary`: a concise, factual handoff summary of the reported theft, cards/accounts the customer identified, verification or lookup status, actions already completed, and the customer's request for urgent human assistance.

This reason takes precedence over lower-tier reasons such as `customer_frustrated_demands_human` or `customer_requests_human_no_specific_reason`.

## Procedure

1. **Recognize the security trigger.**
   Treat a report of a stolen wallet or stolen cards as a fraud/security concern even if the customer has not yet identified a fraudulent transaction.

2. **Review the existing conversation and observations.**
   Use information already supplied by the customer and any already-completed read-only lookups. Do not ask the customer to repeat information already available in the conversation.

3. **Do not delay a requested security transfer.**
   If the customer asks for a human agent in this scenario, transfer promptly. Do not make transfer conditional on finishing identity verification, obtaining card IDs, finding account IDs, card closure, card freezing, or card replacement.

4. **Do not take unapproved irreversible actions.**
   A request to freeze cards does not by itself authorize permanent closure or replacement. Do not close or replace cards unless the customer has clearly authorized that specific action and all applicable policy requirements are met. If the customer declined proposed closure/replacement or insists on a human, include that in the handoff and transfer.

5. **Prepare a minimum-necessary summary.**
   Include only details relevant to helping the receiving agent protect the customer, for example:
   - wallet/card theft reported;
   - the customer says multiple debit and/or credit cards may be affected;
   - the account/card labels the customer provided, if any;
   - whether identity information was provided or verification completed, if known;
   - whether account/card lookup was incomplete because identifiers were unavailable;
   - whether any card action was completed (state “none completed” if none);
   - customer urgently requested a human agent.

   Do not put full payment card numbers, passwords, SSNs, or unnecessary sensitive personal information in the summary.

6. **Call the banking tool exactly once.**
   Invoke `transfer_to_human_agents` with `reason="fraud_or_security_concern"`. After a successful transfer, do not continue card servicing in the same interaction unless the platform explicitly requires it.

## Transfer-summary template
Adapt this to the live conversation; do not invent fields or facts:

> Customer reports a stolen wallet and possible compromise of multiple Rho-Bank cards, including [customer-provided card/account descriptions]. Customer requested urgent human assistance. [Verification/lookup status]. [Actions completed, or “No freeze, closure, or replacement was completed before transfer.”] [Any relevant consent/decline, such as declining permanent closure/replacement]. Please assist with immediate security review and card protection.

## Priority rule
When several transfer reasons might appear applicable, select the highest-priority specific operational reason. For stolen-wallet security escalation, use `fraud_or_security_concern`, not a customer-disposition code.

## Validation before transfer
Confirm all of the following:

- The customer reported theft, loss with security concern, suspected compromise, or potential unauthorized use.
- The customer requested a human agent, or escalation is required by applicable security procedure.
- No claim is made that cards were frozen, closed, replaced, disputed, or otherwise changed unless a corresponding banking tool result confirms it.
- The tool reason is exactly `fraud_or_security_concern`.
- The summary accurately distinguishes customer statements, known lookup results, and actions not yet taken.

## Failure handling
- If the transfer tool reports failure or an unknown outcome, do not assume transfer succeeded and do not repeat an operation reported as `UNKNOWN`. Explain the available safe next step according to the platform’s normal handling.
- If the customer has not requested a human and a direct card-security workflow is available, follow the applicable lost/stolen-card policy instead; this Skill does not authorize card actions by itself.
- If the only issue is a generic preference for a human with no security concern, use the appropriate lower-tier transfer reason rather than this Skill’s security reason.
