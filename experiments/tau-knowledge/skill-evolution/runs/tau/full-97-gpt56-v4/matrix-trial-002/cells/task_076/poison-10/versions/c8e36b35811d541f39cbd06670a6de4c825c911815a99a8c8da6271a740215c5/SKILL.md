---
name: travel-checking-account-recommendation-and-opening
description: Recommend and open a personal checking account for a traveler who wants low international ATM costs and early direct deposit. Use for fact-based product comparison, customer identity verification, consent, and the normal bank account-opening workflow.
---

# Travel Checking Account Recommendation and Opening

Use this Skill for a customer seeking a checking account for travel who specifically values low ATM costs abroad and early access to direct deposits. Provide a recommendation first; opening an account is a separate consequential action requiring verification, eligibility processing, and clear consent.

## Banking control

Banking Knowledge Mandatory Control: Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes.

For a new personal checking account, the relevant controls are the prospective holder's identity and authority, their eligibility, the official product class and its terms, and explicit confirmation to open that exact product. Never treat a lookup by name, email, or ID as identity verification, and never treat a recommendation as consent to open an account.

## Compare products correctly

1. Identify which needs are mandatory. A request for early direct deposit excludes products with no early direct deposit unless the customer explicitly relaxes that requirement.
2. Keep distinct: (a) the bank's foreign-ATM withdrawal fee, (b) its out-of-network ATM fee, (c) an ATM operator's independent surcharge, and (d) a rebate and its cap/timing. Do not describe a third-party surcharge as a bank fee or as guaranteed to be refunded.
3. Compare all documented terms that affect the stated use. Do not use an unsupported assumption about how many withdrawals the customer will make, whether an ATM is in-network, or whether a surcharge will be eligible for a rebate.
4. If an account's early-direct-deposit availability or foreign-ATM pricing is not documented, do not rank it as cheaper or say it meets the request. Say that comparison is unavailable from the current information.
5. State a qualified recommendation, the material tradeoff, and then ask for the exact official account class if the customer wishes to proceed.

### Travel-relevant documented terms

| Official account class | Early direct deposit | Foreign ATM bank fee | Important ATM condition |
|---|---:|---|---|
| Purple Account | Up to 2 days early | $0 per withdrawal | $2.50 for each out-of-network withdrawal; eligible operator-fee rebates up to $30/month after posting; 0.5% currency-conversion markup above interbank rate |
| Green Fee-Free Account | 0 days early | $0 per withdrawal | $0 bank fee for out-of-network withdrawals; operator fees may still apply |
| Evergreen Account | Up to 2 days early | 2%, $3 minimum, per withdrawal | Out-of-network fee is 1%, capped at $2.50 |
| Blue Account | Up to 1 day early | 3%, $5 minimum, per withdrawal | Out-of-network fee is 1%, capped at $3 |
| Green Account (checking) | Up to 1 day early | Greater of 3% or $5, per withdrawal | $3 out-of-network fee |
| Light Blue Account | Not established here | First 2 foreign withdrawals monthly free, then $4 each | Do not say it satisfies early-direct-deposit needs without evidence |

For a traveler who requires early direct deposit, **Purple Account** is the strongest documented recommendation among the products with documented terms above: eligible direct deposits can arrive up to two days early and the foreign ATM withdrawal fee is $0. Explain the limitation plainly: withdrawals at non-Rho ATMs can still incur the $2.50 bank out-of-network fee; an operator may charge a separate surcharge; eligible operator-fee rebates are posted later and limited to $30 per month; and currency conversion carries a 0.5% markup above the interbank rate. This markup is distinct from an ATM withdrawal fee.

If the customer instead prioritizes eliminating the bank's ATM fees over early deposit, identify **Green Fee-Free Account** as the alternative: it has $0 bank fees for foreign and out-of-network ATM withdrawals, but provides no early direct deposit. Do not call it the better fit while early deposit remains required.

## Identity verification before opening

1. Obtain an identifier: exact full name, user ID, or email. Call only the corresponding customer lookup tool (`get_user_information_by_name`, `get_user_information_by_id`, or `get_user_information_by_email`). If there is no unique match, stop and obtain a usable identifier.
2. Ask the customer to supply—not merely confirm—two of these four fields: date of birth, email, phone number, or address. Do not disclose lookup values in the prompt. Compare the supplied values to the record, allowing harmless presentation differences such as a spelled-out date versus its numeric form.
3. If two fields match, call `get_current_time`, then call `log_verification` with the complete authoritative record and that returned timestamp. Only after a successful log result may identity be treated as verified.
4. If fewer than two fields match, or logging fails, do not open an account. Ask for the needed fields or explain that identity verification could not be completed.

## Eligibility and consent

Personal checking requires all of the following: verified customer; age 18 or older; no more than four personal checking accounts; and no checking account closed for cause in the prior six months.

Use authoritative bank processing for these facts. The date of birth can establish age after identity verification. Do **not** ask a customer to self-attest to internal status such as verification, account count, or closure-for-cause history: those are bank-held facts, and a customer assertion is not an eligibility check. Where no separate eligibility-lookup tool is available, the documented opening workflow is the authoritative workflow that performs those checks before it creates an account. Do not claim the internal conditions passed until that workflow returns a successful opening result. If it reports a failure or ineligibility, do not retry or promise an opening.

Before opening, obtain unambiguous consent that names the exact official account class, for example: “I want to open the Purple Account.” Phrases such as “whichever is cheapest” or “sounds good” are insufficient. The value must retain its full official name, including `Account`.

## Open the account

After successful identity verification and exact consent, submit the request through the documented workflow. This is appropriate only because the workflow applies the bank-held personal-checking eligibility checks before creating the account; it is not a substitute for identity verification or consent.

1. Unlock `open_bank_account_4821` with `unlock_discoverable_agent_tool` if it has not already been unlocked.
2. Use the unlocked tool via `call_discoverable_agent_tool` with only its documented required arguments:
   - `user_id`: the verified customer's ID;
   - `account_type`: `checking` for a personal checking account;
   - `account_class`: the explicitly selected full official name, such as `Purple Account`.
3. Treat the tool's result as authoritative. It performs the remaining bank eligibility processing. Never invent extra parameters or retry an uncertain or failed submission.
4. On success, report that the account was opened and only the actual returned details. On a decline or error, say that it was not opened and give only the supported next step.

## Customer-facing response pattern

- **Recommendation:** Name the recommended class, early-deposit timing, foreign ATM fee, separate out-of-network/operator-fee/rebate limits, and the distinct 0.5% currency-conversion markup when the customer needs a full travel-cost picture.
- **Verification request:** Ask for two identity fields without revealing them.
- **Consent request:** After verification, ask the customer to explicitly confirm the full account class.
- **Successful opening:** State the actual opening result and briefly remind the customer that eligible direct deposits may arrive up to two days early. To set up direct deposit, they can obtain account and routing numbers in online or mobile banking and provide them to the payer under the payer's enrollment process.

## Completion check

Before a final answer, ensure that the terms were not conflated, identity was logged using two matching fields, the account class was explicitly selected, and the opening status precisely matches the opening-tool response.
