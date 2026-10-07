---
name: open-personal-checking-account
version: 1.0.0
description: Safely answer product questions and open an additional personal checking account after identity, eligibility, product selection, fees, and final authorization have been verified. Use for a customer who asks to open a personal checking account or needs help selecting one before opening.
---

# Open a Personal Checking Account

Use this workflow to provide accurate product guidance and, only after all required checks and explicit authorization, open a personal checking account.

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

## Scope and safety rules

- Treat a request for product information as informational until the customer explicitly selects an account and authorizes opening it.
- A supplied name, email, or profile lookup result identifies a possible customer but does not itself complete identity verification. Obtain confirmation of two of these four profile fields: date of birth, email address, phone number, and street address.
- Do not expose unconfirmed profile values while asking for verification. Ask the customer to provide or confirm the values.
- Do not open an account based on an implied preference, a question about a product, or an earlier request that did not name the final product.
- Use only the available normal banking tools. Do not attempt account opening through a script or recommend that a script causes a banking action.
- If required information is missing, inconsistent, the profile is ambiguous, eligibility is not met, a tool fails, or the customer does not give final confirmation, pause and explain the specific next step. Do not open the account.

## Product guidance

Answer the customer’s question from the applicable product materials before requesting a selection. State material conditions that matter to their stated need, including fees, withdrawal/decline behavior, transfer fees, limits, and timing qualifications.

For example, when comparing a checking product that has no account overdraft fee but supports linked-account overdraft-protection transfers with a product that declines transactions rather than transferring funds:

1. Explain that no account overdraft fee does not necessarily mean every shortfall is covered.
2. State that overdraft protection requires an eligible linked funding account and that each protection-triggered transfer has its disclosed per-transfer fee.
3. Explain that a no-overdraft product may decline transactions that exceed available funds instead of transferring money from savings.
4. For early direct deposit, state the documented availability and qualification (for example, that it may post up to the stated number of days early depending on payer submission), rather than guaranteeing a particular weekday or deposit date.
5. Ask the customer to choose the full official account class name after answering.

If the customer’s needs conflict with a product’s documented behavior, clearly identify the conflict and offer the supported alternatives. Never claim an unavailable feature or waive a disclosed fee.

## Required opening workflow

### 1. Identify the customer and verify identity

1. Obtain a unique profile identifier by asking for the customer’s full name or email address.
2. Use the matching customer lookup tool (`get_user_information_by_name` or `get_user_information_by_email`) to find the profile.
3. If zero or multiple profiles are returned, request enough information to resolve the ambiguity without disclosing profile data.
4. Ask the customer to confirm two of the four identity fields: date of birth, email, phone number, or street address.
5. Compare both provided fields with the retrieved profile. If either does not match, do not proceed; request correction or use the applicable escalation process.
6. Get the current timestamp with `get_current_time`, then create the audit record with `log_verification`, supplying the retrieved profile values, user ID, and timestamp.

### 2. Confirm the requested account and authorization

1. Ask for the desired personal checking `account_class` using its complete official name ending in `Account` (for example, `Blue Account` or `Green Account (checking)`).
2. If the customer is still comparing products, provide guidance and wait; do not interpret a product question as selection.
3. Before performing the opening action, summarize the exact account class and material disclosed terms relevant to the customer’s requirements.
4. Obtain clear final authorization to open that exact account. A response such as “yes, open [full account class]” is sufficient; silence, a question, or a general interest statement is not.

### 3. Check eligibility

After identity verification and before opening, retrieve all checking and savings accounts for the verified user with `get_all_user_accounts_by_user_id_3847`. If it is an agent-discoverable tool in the runtime, first unlock it through `unlock_discoverable_agent_tool`, then invoke it through `call_discoverable_agent_tool` using the verified `user_id`.

Confirm all of the following:

- The customer is verified.
- The customer is at least 18 years old.
- The customer has no more than 4 existing personal checking accounts; opening another must not exceed the allowed maximum of 4.
- The customer has not had a checking account closed for cause during the preceding 6 months.
- The requested account class is a supported personal checking product and is supplied in its full official form ending in `Account`.

Use account status, account class/type, and opening/closure information returned by the account query where available. If the returned data cannot establish the closed-for-cause requirement or account count, do not infer eligibility; obtain the required supported record or explain that opening cannot proceed through this workflow.

### 4. Open the account

Only when every prerequisite above is satisfied and the customer has given final authorization:

1. Access `open_bank_account_4821` using the runtime’s documented discoverable-agent-tool process if necessary.
2. Invoke it with the verified customer identity and the exact selected `account_class`, using only the tool’s documented required arguments.
3. Report the result faithfully. Confirm the account class and any account identifier returned by the tool, but do not invent an account number, opening date, balance, or enrollment.

If the opening tool returns an error or uncertain outcome, do not retry blindly and do not state that an account was opened. Explain that the request did not complete and follow the available error/escalation procedure.

## Overdraft-protection follow-up

Opening a checking account and enrolling linked-account overdraft protection are separate actions. If the customer asks for protection:

- First verify that the selected checking product supports it.
- Confirm the customer owns and is authorized to use an eligible linked funding account.
- Disclose the per-transfer fee and explain that it applies for each protection-triggered transfer.
- Obtain separate confirmation before enabling the service.
- If the product instead declines transactions that exceed available balance and has no automatic transfers, say so plainly and do not attempt to enable overdraft protection.

## Customer response template

Use concise, factual language adapted to the selected product:

> I can help with that. [Product] has [relevant early-deposit timing, qualified by payer processing] and [relevant overdraft behavior]. [If applicable: Linked overdraft protection requires an eligible linked account and costs [fee] per transfer.] If you would like to open it, please confirm that you want the full account name, “[full official account class],” and I’ll complete identity and eligibility checks before opening it.

## Validation checklist

Before any account-opening call, verify all boxes are true:

- [ ] One unambiguous customer profile was identified.
- [ ] Two identity fields were actively confirmed and matched.
- [ ] `log_verification` was recorded with a current timestamp.
- [ ] The customer is eligible by age, checking-account count, and closure history.
- [ ] The exact official personal checking account class was selected.
- [ ] Relevant fees, limits, early-deposit qualification, and overdraft behavior were disclosed accurately.
- [ ] The customer gave explicit final authorization for that exact account.
- [ ] The opening action will use `open_bank_account_4821` through normal banking tools.

If any box is unchecked, continue clarification or stop; do not open the account.
