# Guidance for SC-100-style Small Claims forms

These notes help map a plaintiff's case description to the real field names
discovered by `inspect_fields.py`. Always trust the live field names,
types, states, and tooltips over any assumption here.

Typical semantic groups on SC-100 (names vary; match by tooltip/field name):
- Plaintiff (the person suing): full name, mailing/street address, city,
  state, ZIP, phone, email.
- Defendant (the person being sued): name, street address, city, state,
  ZIP, phone.
- Claim amount: the dollar figure being sued for (digits only unless the
  field clearly expects a formatted value).
- Reason / "why does the defendant owe you money": a short narrative.
- "How did you calculate the money owed": brief basis statement.
- Dates: when the event/dispute happened ("from" / "until" dates) and the
  form filing date. Convert to the requested format (ISO YYYY-MM-DD when the
  instruction says xxxx-xx-xx).
- Venue / "why are you filing in this court": one checkbox/radio choice such
  as the option for where the defendant lives or does business. Pass the
  exact on-state string from that field's `states`.
- "Have you filed more than 12 claims..." / number of prior small-claims
  cases this calendar year: for a first-time filer this is typically the
  "No" / zero option; set the matching checkbox or numeric field only if the
  instruction supplies the fact.
- "Are you asking the court to..." and other clerk/attorney/court-use fields:
  leave empty unless the instruction explicitly provides them.

Rules:
- Fill only fields the instruction supports; leave everything else empty.
- A checkbox is only "checked" when its value equals one of its on-states.
  Verify with verify_fields.py that the stored value is the on-state.
- If a requested fact has no matching field, note it as unsupported instead
  of overloading an unrelated field.
