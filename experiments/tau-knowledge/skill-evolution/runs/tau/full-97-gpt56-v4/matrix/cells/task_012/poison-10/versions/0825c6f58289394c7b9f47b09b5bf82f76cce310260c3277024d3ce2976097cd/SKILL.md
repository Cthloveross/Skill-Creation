---
name: travel-readiness-with-limited-card-support-information
description: Provide evidence-grounded general pre-travel guidance for a cardholder when card materials document fraud monitoring and international-use alerts but do not document travel-notification setup, app access, forms, or timing. Transfer a customer who expressly asks for a human agent.
---

# General International Travel Card Readiness

## When to use
Use for a customer asking how to avoid an international-card decline or how to set a travel notification, where the supplied card materials do **not** give a travel-notification procedure. This is general card guidance, not an account lookup or a card-management action.

Read the latest customer message, supplied card documentation, and completed tool observations. A name, planned destination, approximate dates, or an unsuccessful lookup does not establish an account or authorization to act on one.

## Method

1. Answer the customer's current question directly. If the supplied materials do not document travel-notification availability, an app route, a form, travel dates required, or a lead time, say that there is no documented process available to confirm those details. Do not infer from silence that notification is required, not required, already submitted, or unavailable.
2. Give the documented preparation that is relevant to international travel: recommend transaction and international-use alerts and current contact details. Explain that real-time monitoring can flag unusual activity and ask the cardholder to verify it. Prompt attention to a verification request can help with a flagged transaction, but cannot guarantee approval of every transaction.
3. If the evidence states a fraud-alert response target, it may be quoted accurately as a target, not a promise. Do not introduce other card features, deadlines, URLs, menu paths, countries, or authorization rules unless the current evidence states them.
4. Do not collect or retry personal data for this general answer. Do not ask a customer without fixed dates to guess dates. If they later want an account-specific action, first meet the declared identity-verification requirements and use only the declared banking tools.
5. If the customer explicitly asks for a human agent, call `transfer_to_human_agents`. Use `customer_requests_human_no_specific_reason` unless a more specific reason is documented. The summary should state only the general request, that the available card materials do not specify the travel-notification workflow, and any relevant completed verification status. After a successful transfer, send one brief confirmation that the customer is being connected, then stop; do not speculate further.

## Grounded answer pattern
Adapt to the actual evidence:

> I can share the travel-readiness information that is documented for your card. I do not have a documented app path, form, or advance-notice requirement for a travel notification, so I cannot confirm those details. For international travel, enable transaction and international-use alerts and make sure your contact details are current. Unusual activity can trigger a verification prompt; responding promptly can help address a flagged transaction, although it cannot guarantee every purchase will be approved.

## Safety checks
Before responding, verify that the response:

- does not claim that a notification was made, is mandatory, or is unnecessary;
- does not invent a workflow, deadline, or card/account status;
- includes only facts supported by the supplied card documentation;
- does not request unnecessary personal information; and
- transfers and confirms the connection when the customer expressly requests a human.
