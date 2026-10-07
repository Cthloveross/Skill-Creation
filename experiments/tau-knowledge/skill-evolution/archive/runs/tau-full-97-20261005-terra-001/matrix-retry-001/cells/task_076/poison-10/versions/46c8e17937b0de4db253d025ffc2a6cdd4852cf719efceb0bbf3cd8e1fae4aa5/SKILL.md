---
name: authorized-personal-checking-opening
description: Verify documented eligibility evidence and open an authorized personal checking account using the bank's account-opening tool. Use when a customer has selected an exact checking account class and authorized the opening, including when those facts are supplied in a conversation transcript or public task inputs.
---

# Authorized Personal Checking Account Opening

Use this skill to complete—not merely describe—an authorized personal checking-account opening. Product comparison is complete once the customer has selected an account. Do not reopen the comparison or request redundant confirmation after valid selection and authorization are already present.

## Banking control

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this account-opening workflow, the applicable prerequisites are identity, authority, personal-checking eligibility, the selected account class, applicable fees and limits, and explicit authorization. Account ownership, balances, recipient details, transfer cutoffs, and card details are not prerequisites to opening an unfunded personal checking account unless the current bank procedure or tool response specifically requires them.

## Runtime inputs and evidence

Read the current task inputs, conversation, and prior read-only observations at runtime. Do not hardcode customer identifiers or infer missing facts.

Collect the following evidence:

- A unique customer record and its `user_id`, obtained through an authenticated customer lookup or a successful supplied lookup observation.
- Identity/verification evidence required by the runtime. A statement that the profile is verified can establish the documented checking-eligibility condition when the task supplies it; follow any stricter live authentication requirement if one exists.
- Age evidence from the on-file date of birth and the supplied or retrieved current date.
- Confirmation that the customer has no more than four personal checking accounts.
- Confirmation that no checking account was closed for cause during the prior six months.
- The exact personal checking `account_class` selected by the customer, using its full official name ending in `Account`.
- Explicit authorization to open that selected class.

Use a unique successful profile lookup to bind the selected account and authorization to the customer record. If the current inputs already contain a unique lookup, verified-profile confirmation, the eligibility confirmations, a selected full account class, and authorization, use those supplied facts; do not make the customer repeat them solely because they appeared in an earlier clarification.

If identity, authority, eligibility, selection, or authorization is absent, contradictory, ambiguous, or failed, do not open the account. Explain the specific missing prerequisite and obtain it through an authorized process.

## Personal checking eligibility

Confirm all of these before opening:

1. The customer is verified.
2. The customer is at least 18 years old on the current date.
3. The customer does not exceed four personal checking accounts.
4. The customer has no checking account closed for cause in the previous six months.

Use returned account data when it is available and needed to resolve an eligibility question. The account-information procedure identifies `get_all_user_accounts_by_user_id_3847` as the source for account type, status, balance, and date opened; use it where available instead of guessing. Do not substitute the savings-account eligibility procedure for this checking-account workflow.

## Product facts to disclose when Purple Account is selected

For the documented Purple Account, accurately state only the applicable documented facts:

- Eligible direct deposits may arrive up to two days early.
- There is no Rho-Bank foreign ATM withdrawal fee.
- Eligible posted ATM-operator fees may be rebated up to $30 per month; third-party operator fees can still apply and rebate amounts are not guaranteed beyond the monthly cap.
- The monthly maintenance fee is $15 and is waived only with a $3,750 minimum daily balance.
- The daily ATM withdrawal limit is $1,000.

Do not claim that the monthly fee is waived when the customer cannot maintain the required balance. Do not invent third-party ATM surcharge amounts or unverified account-opening requirements.

## Required execution procedure

1. **Identify and bind the customer.** Locate one matching customer record using the available user lookup, or use the successful unique lookup supplied in the task inputs. Extract the runtime `user_id`. Stop for ambiguity or no match.
2. **Verify prerequisites.** Evaluate the identity/verified-profile evidence, age, checking-account count, closure-for-cause history, fees and limits, selection, and authorization. Record or summarize the evidence without unnecessarily exposing full date of birth, address, phone number, or email in the customer-facing response.
3. **Confirm the exact class.** The opening class must exactly match the customer-selected official class string and end in `Account`. Do not shorten, translate, normalize, or replace it with a different account type.
4. **Perform the banking action.** Once all prerequisites are satisfied, unlock `open_bank_account_4821` with `unlock_discoverable_agent_tool`. Then call it through `call_discoverable_agent_tool` using:
   - `agent_tool_name`: `open_bank_account_4821`
   - `arguments`: a JSON object containing the runtime customer `user_id`, `account_type` set to `checking`, and the confirmed full `account_class`.

   This is an agent banking action. Do not give the tool to the customer and do not stop after describing how it would be called. Ensure the actual `open_bank_account_4821` tool-call event is emitted in the execution trace after authorization.
5. **Handle the result.** Report success only if the opening tool reports success. Provide any returned account details that are appropriate to share, plus the relevant fees, waiver condition, limits, and travel-fee caveat. If the tool returns an error or is unavailable, do not retry blindly and do not state that an account was created; report the failure and the appropriate next step.

## Immediate-completion rule

When the supplied interaction already establishes a unique customer record, checking eligibility, an exact selected checking class, and explicit authorization, proceed directly to the opening-tool action. Do not replace the action with another recommendation, a generic greeting, an explanation of the procedure, or a request for confirmation that is already present.

## Validation checklist

Before the tool call, verify all answers are yes:

- Is there exactly one customer record and a runtime `user_id`?
- Is identity/verified-profile evidence sufficient under the current runtime requirements?
- Is the customer at least 18?
- Is the checking-account limit satisfied?
- Is the closure-for-cause condition satisfied?
- Is the selected class the full official checking account name ending in `Account`?
- Did the customer explicitly authorize opening that exact class?

Validate the action payload before sending it:

```json
{
  "user_id": "<runtime customer user_id>",
  "account_type": "checking",
  "account_class": "<exact customer-selected full official class>"
}
```

After the call, validate that the execution trace contains an assistant call named `open_bank_account_4821` with structured arguments matching the verified runtime `user_id`, `account_type: "checking"`, and the exact selected `account_class`.

## Failure handling

- **Ambiguous customer lookup:** obtain a valid identifier and repeat the lookup; do not choose among multiple records.
- **Identity or eligibility failure:** do not open the account; explain only the relevant unmet requirement.
- **Missing authorization or account class:** obtain explicit authorization and the exact full official class before acting.
- **Tool failure:** do not claim success, fabricate an account identifier, or attempt unrelated banking actions.
- **No additional funding instruction:** do not transfer funds as part of personal checking opening unless a separate documented procedure and customer authorization require a transfer.
