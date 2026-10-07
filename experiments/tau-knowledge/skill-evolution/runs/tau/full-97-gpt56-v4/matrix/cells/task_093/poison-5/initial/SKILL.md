---
name: savings-interest-history-guidance
description: Assist a customer who questions savings interest payments but does not have the statement date, interest-credit amount, balances, or transaction details. Use when the available bank tools cannot retrieve checking/savings history, and provide only supported ways to obtain that history.
---

# Savings Interest and Transaction-History Guidance

## Purpose

Help customers investigate a possibly low savings-interest payment without guessing account data, rates, eligibility, calculations, statement contents, or online-banking navigation that is not supported by the available knowledge.

## Inputs

Use the current conversation plus any explicitly provided public observations. Identify:

- The product the customer believes is affected (for example, savings).
- Whether they have supplied a statement month/date, interest-credit amount, account identifier, or balance history.
- Whether the available tools actually expose checking/savings accounts or their transactions.
- What the customer is now asking for: an explanation, a lookup, transaction history, a statement, or general access guidance.

Do not treat an email address or account name alone as authorization to disclose account information. Follow the runtime's identity-verification and logging requirements before disclosing nonpublic account information if a suitable account-data tool is available.

## Procedure

1. **Acknowledge the concern clearly.** State that interest can be reviewed once the relevant savings interest-credit entry and statement-period details are available.
2. **State the access limitation accurately.** If the supplied tools do not provide checking/savings account balances, statements, or transaction history, say that you cannot look up or verify the payment from the available tools. Do not infer that credit-card records reveal savings activity.
3. **Give supported self-service and support routes.** Explain that recent transactions are available in the Rho-Bank mobile app or online banking portal. For a complete checking or savings transaction history, including interest payments, direct the customer to contact Rho-Bank through one of these supported channels:
   - phone: `1-800-RHO-BANK`
   - chat through the Rho-Bank mobile app
   - online help center: `rhobank.com/help`
4. **Answer navigation/download questions conservatively.** Do not invent portal menu names, buttons, download formats, or statement-download steps. Say that the customer can use online banking to view recent transactions; if they need the complete history or cannot find a statement/download option, they should use the listed support channels to request the history or obtain assistance.
5. **Make the next review actionable.** Ask the customer to obtain and share, or provide to the representative, the statement month (or interest-credit date and amount) and relevant savings transaction entries. If the customer has it, an account identifier and major balance changes during the period can help contextualize the review. Do not promise a calculation or correction without data and applicable product terms.
6. **Avoid unnecessary escalation.** Do not transfer merely because historical savings data is unavailable in the provided tools. Offer the supported contact routes. Transfer only when the user requests a human agent or a runtime/policy requirement independently calls for it.

## Required response qualities

- Be transparent that a lookup was not performed when no qualifying tool exists.
- Do not claim that a statement was downloaded, transaction history was accessed, or interest was checked unless a declared tool actually returned it.
- Do not disclose personal information acquired from lookup tools unless necessary and permitted for the immediate task.
- Do not provide unsupported APY figures, pairing benefits, rate formulas, or account-specific conclusions.
- Keep contact details exact and include all three supported routes when directing the customer to complete history.

## Response template

Adapt this wording to the conversation:

> I understand why you want to check the savings interest credit. I do not have access to savings-account balances, statements, or savings transaction history through the tools available here, so I cannot look up or verify the payment.
>
> You can view recent transactions in the Rho-Bank mobile app or online banking portal. For a complete savings transaction history, including interest payments, please call 1-800-RHO-BANK, chat with us in the mobile app, or visit rhobank.com/help. A representative can help retrieve the relevant history.
>
> When you have it, the statement month or the date and amount of the interest-credit transaction will let us focus the review. If you cannot locate a statement or download option in online banking, please use one of those support channels for help obtaining it.

## Validation checklist

Before sending a response, verify all of the following:

- The response does not assert access to savings data when no savings-data tool was supplied.
- It identifies the mobile app and online banking portal as places for recent transactions.
- It directs complete-history requests to phone, mobile-app chat, or `rhobank.com/help`.
- It includes `1-800-RHO-BANK` exactly when giving the support routes.
- It does not invent online-banking navigation or download instructions.
- It does not invent account-specific interest details, rates, or conclusions.
