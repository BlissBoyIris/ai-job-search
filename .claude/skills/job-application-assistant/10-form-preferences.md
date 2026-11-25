# Form Preferences

Standing answers and rules for application forms. `/fill` reads this file **first**, and it wins over every other source. `/fill` Step 7 adds rules here from your edits to the end-of-day report. Each learned rule carries the date it was added in brackets. When a new rule contradicts an old one, the old one is replaced.

Every answer here must stay true to `01-candidate-profile.md`. This file decides *how* to answer, never *what happened*.

<!-- SETUP: Fill in the brackets, or delete a line you'd rather /fill draft and mark ⚠ each time. Lines left as [PLACEHOLDERS] are ignored. -->

## Contact and identity
- Full name: [YOUR_NAME] (first: [FIRST_NAME], last: [LAST_NAME])
- Email: [YOUR_EMAIL]
- Phone: [YOUR_PHONE]
- LinkedIn: [YOUR_LINKEDIN_URL]
- Website / portfolio: [YOUR_WEBSITE_OR_BLANK]
- Location / city: [YOUR_CITY], [YOUR_COUNTRY]
- Time zone: [YOUR_TIME_ZONE] and the hours you can overlap
- Pronouns: leave blank unless required; if required, ⚠ and ask.

## Availability
- Notice period / start date: [YOUR_NOTICE_PERIOD]
- Currently employed? (yes/no): [YES_OR_NO]

## Work setup and authorization
- Work mode wanted, willing to relocate: [REMOTE / HYBRID / ON-SITE; RELOCATE YES/NO]
- Work authorization: [WHERE_YOU_CAN_WORK_AND_ON_WHAT_BASIS]
- "Do you need visa sponsorship?": [YOUR_ANSWER]
- "Are you authorized to work in <a country you have no work rights in>?": answer truthfully (No), and mark ⚠ with a toDo: "Form asks for <country> work rights. Still send?"

## Compensation
- Range: [YOUR_RANGE_AND_PERIOD]
- Single number: [YOUR_SINGLE_NUMBER]
- Never quote below your pay floor in `my_search.json`. If the posting states a range above the floor, a figure inside that range is fine. Mark it ⚠.
- Currency fields: [YOUR_CURRENCY] unless the form forces another, then convert and mark ⚠.

## Background
- Years of experience: [YEARS]
- Highest education: [DEGREE, SCHOOL, YEARS]
- Languages: take them from the Languages table in `CLAUDE.md`.

## Common questions
- "How did you hear about us?": the board the job came from if it is an option. Otherwise "Job board".
- "Referred by an employee?": No, unless the job's saved answers say otherwise.
- Voluntary demographic questions (gender, ethnicity, veteran, disability): "Decline to answer" / "Prefer not to say".
- Consent, terms, privacy and declaration checkboxes: never tick. List them in the report as "Tick: <label>".
- Optional "anything else?" boxes: leave blank unless the job's saved answers cover it.

## Learned rules
<!-- /fill Step 7 adds rules here, one per line, with the date in brackets. -->
