---
name: coordinated-bank-account-change-request
description: Safely handle a customer request that combines account closures with personal-savings and business-checking openings. Use this skill when identity must be verified and each requested action must be separated into documented, authorized, tool-supported steps.
---

# Coordinated Bank Account Change Request

Use this workflow for a multi-part banking request involving account closures and/or new business or personal accounts. Treat every requested action as independent: completing, deferring, or escalating one must not authorize another.

## Mandatory banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Inputs and runtime assumptions

Read the current customer conversation, any prior clarifications, read-only observations, and available tool schemas at runtime. Do not treat a profile lookup by name or email as identity verification. Do not reuse identifiers, balances, account details, or conclusions from another request.

The workflow may use the following supported functions when present:

- Profile lookup tools to locate a candidate profile.
- `log_verification` after identity is verified.
- The documented savings-opening tools `open_bank_account_4821` and `transfer_funds_between_bank_accounts_7291`.
- `transfer_to_human_agents` when a requested operation lacks a documented procedure or supported tool.

Do not invent an account closure, business-account opening, product-search, card-linking, fee-waiver, or account-enrollment tool. Do not represent an informational product description as approval or a completed banking action.

## 1. Establish identity and scope

1. Locate the customer only from identifying information they provide, using an available profile lookup tool.
2. Ask the customer to confirm two of the four identity fields required by the runtime: date of birth, email, phone number, or address. Compare the supplied values with the returned profile. Do not reveal unconfirmed values.
3. Once two fields match, obtain the current time with `get_current_time` and call `log_verification` with the complete profile fields returned by the lookup and that timestamp.
4. Confirm the distinct requested actions, their order if material, and the customer's authority for each account. A customer's broad statement that they want an overhaul is not confirmation to close a specific account.

Do not take any account-opening, closing, or transfer action until verification, authority, ownership, required prerequisites, and explicit confirmation for that individual action are all established.

## 2. Respond to product questions before acting

When the customer asks whether the Green Account (savings) supports a given withdrawal pattern, give only the documented facts:

- The standard Green Account allowance is at most 8 free withdrawals each month.
- A customer who holds an eligible EcoCard linked to the Green Account and keeps it in good standing receives 7 additional free withdrawals, for 15 total free withdrawals monthly.
- Withdrawals above 15 are not free.
- An EcoCard holder may receive up to $20 in monthly ATM-fee rebates.
- Green Account pays 4.0% APY; an eligible EcoCard adds 0.5% while eligibility is maintained.

Do not say that a customer has the enhanced allowance merely because they expect 10--15 withdrawals. Determine card status from supported account/card records when available. If no eligible linked EcoCard is established, describe the standard eight-withdrawal allowance and do not promise the enhanced benefits. If the customer needs more than the applicable free allowance, disclose that the excess is not free; do not fabricate an excess fee amount.

For a Green Account recommendation, disclose the known terms: $100 minimum opening deposit, $500 ongoing minimum balance, daily interest compounding, paperless statements required, and no monthly maintenance fee even if the minimum is not met. Confirm that the customer accepts the product and paperless statements after discussing these terms.

## 3. Personal Green Account opening procedure

Perform these steps only after the customer explicitly chooses and confirms the Green Account:

1. Verify the customer is eligible for a personal savings account: verified identity; at least one active Rho-Bank checking account; fewer than five personal savings accounts; no accounts in collections or with negative balances; and a checking-account tenure of at least 14 days.
2. Verify the required account records, ownership, and the exact official account class. The documented class must use the full official name ending in `Account`; for this product use `Green Account` only when that is the confirmed official product selection.
3. Confirm paperless-statement enrollment and confirm the opening-deposit arrangement. The required deposit is at least $100.
4. Call `open_bank_account_4821` with the authenticated customer ID, `account_type` set to `savings`, and the confirmed account class.
5. Ask whether the customer authorizes an immediate opening-deposit transfer from a specified eligible checking account. If yes, verify the source-account ownership, available balance, amount (at least $100), destination account, and confirmation, then call `transfer_funds_between_bank_accounts_7291`.
6. If the customer declines immediate transfer, state that the account must be funded within 30 days through internal transfer or external deposit or it will be closed. Do not transfer funds without authorization.
7. Provide the resulting account details and accurate funding status or funding deadline.

If any eligibility check fails, do not open the account. Explain the applicable unmet condition without exposing unnecessary account information.

## 4. Account-closure requests

For each requested closure, first verify the exact account identifier, account ownership and authority, current balance, negative balance or collections status, pending transactions, linked obligations, destination/settlement details, applicable fees or cutoffs, and the customer's final confirmation.

Only use a closure workflow and closure tool when both are explicitly documented and available in the current runtime. If no supported closure procedure/tool is supplied, do not claim to have closed the account and do not infer a way to do so. Escalate with `transfer_to_human_agents` using `account_closure_request`, with a concise summary of the verified customer request, the specific account(s), and that no documented closure capability is available. Do not include unnecessary full identity data in the summary.

## 5. Business-checking requests

Business checking requires distinct business eligibility, entity documentation, ownership/beneficial-owner information, authorized-signer authority, exact account product, pricing, and formation-date requirements. Do not substitute personal-savings eligibility for business-account eligibility.

If the customer requests a permanently free regular business account, do not promise that such a product exists or recommend a startup/free-trial offering without current, documented product terms. Ask for the entity formation date and required documents only when a documented business-account process requires them. When the runtime does not provide a business-account product catalog, eligibility policy, or supported opening procedure, explain that the available information cannot verify a suitable product or open it, then escalate the business-account portion with `specialized_department_required`.

## 6. Customer communication and completion

Give a clear status for every requested item: completed, awaiting customer confirmation/information, blocked by an eligibility requirement, or escalated. In particular, a product-information answer does not constitute consent to open an account, and a request to close an account does not authorize transfers needed to settle it.

If multiple matters must be escalated and one supported transfer is appropriate, summarize all outstanding closure/business-account needs in the handoff while preserving the independent status of the personal-savings request. Do not transfer or close accounts merely to simplify a combined request.

## Validation checklist

Before stating that any action is complete, confirm all of the following:

- Identity verification was performed using two matching required identity fields and recorded with `log_verification`.
- The customer authorized the exact action and the affected account is owned by them.
- Product facts, eligibility, account class, paperless requirement, and funding arrangement were checked for a Green Account opening.
- Any fund transfer had a verified source, destination, available balance, amount, and explicit authorization.
- No closure or business-opening action was claimed without a documented procedure and supported tool.
- The final response separately reports the status and next step for every requested closure and opening.
