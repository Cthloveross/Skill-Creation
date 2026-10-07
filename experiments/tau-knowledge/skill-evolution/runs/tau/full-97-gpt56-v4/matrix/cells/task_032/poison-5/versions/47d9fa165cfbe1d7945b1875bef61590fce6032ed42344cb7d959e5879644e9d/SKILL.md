---
name: card-purchase-decline-triage
description: Explain likely causes and safe next steps when a customer reports credit-card purchase declines despite available credit. Use for general declined-purchase questions when no verified account-specific diagnosis is available.
---

# Card Purchase Decline Triage

## Purpose
Provide accurate, non-diagnostic help for a cardholder whose purchase is declined even though their available credit appears sufficient. Available credit alone does not establish why an authorization was declined.

## Runtime input
Use the current customer conversation as input. This Skill does not require a script or account lookup for a general explanation.

Expected information, if supplied voluntarily, may include:
- whether the card is new or a replacement;
- whether the card may be expired;
- whether the purchase is international or unusual for the customer;
- whether the problem occurs at more than one merchant/terminal;
- whether the customer has received a fraud-verification alert.

Do not request full card numbers, CVVs, passwords, or other unnecessary sensitive data. Do not claim to see an account, fraud flag, limit, or transaction result unless an authorized runtime tool has actually returned it.

## Response method
1. Acknowledge the disruption and clarify that a decline can happen even with available credit.
2. Explain the supported possibilities in plain language:
   - fraud/security monitoring may flag an unusual transaction and require verification;
   - a merchant terminal or entry error may be at fault;
   - a newly issued or replacement card may not be activated;
   - the card may be expired;
   - international-use restrictions may apply; or
   - a temporary processing/technical issue may have occurred.
3. Give these safe first checks, without representing them as a diagnosis:
   - recheck the entered card details, expiration date, and CVV;
   - retry once in case of a temporary issue;
   - confirm activation if the card is new or replacement;
   - check the expiration date; and
   - if practical, try another terminal or merchant.
4. For an unusual transaction or an alert, tell the customer to respond promptly to the verification request using the bank's legitimate channel. Do not advise bypassing security checks.
5. If declines persist, occur across merchants, or the customer is concerned about fraud, recommend prompt contact with customer service for account review, including fraud alerts, holds, restrictions, and transaction details. Per the supplied support guidance, the customer can call **1-800-RHO-BANK**, use in-app chat, or visit **rhobank.com/help**. If the active runtime requires/permits an agent handoff and the customer wants it, use its supported human-transfer process with the most applicable reason; otherwise offer these channels.

## Suggested customer-facing answer
Adapt this wording to the conversation:

> I’m sorry you’re dealing with that. Having available credit does not always prevent a decline. A transaction can be stopped by fraud monitoring (especially if it looks unusual), a merchant terminal or entry problem, a card that needs activation or has expired, international-use restrictions, or a temporary processing issue.
>
> Please first double-check the card details, expiration date, and CVV; retry once; confirm activation if this is a new or replacement card; and, if possible, try another terminal or merchant. If you received a fraud-verification alert, respond to it promptly through the legitimate bank channel.
>
> Since this has kept happening, customer service should review the account for any fraud alert, hold, or restriction and help identify the specific decline. You can call 1-800-RHO-BANK, use in-app chat, or visit rhobank.com/help.

## Validation before responding
Ensure the final response:
- says that available credit is not the only approval condition;
- includes only supported possible causes, not a definitive unsupported cause;
- gives at least one practical check and a clear escalation path for persistent declines;
- does not expose or solicit sensitive card credentials; and
- does not promise that a retry, alert response, or contact channel will approve a transaction.

## Unsupported cases
This Skill cannot determine a specific decline reason from available credit alone. It must not invent account status, transaction history, spending-limit settings, fraud decisions, or an international restriction. Escalate through supported customer-service channels when an account-specific review is needed.
