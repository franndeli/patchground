# Human acceptance trial kit

Two short sessions with real people close the remaining launch gate. Synthetic learners have already
exercised the mechanics ([cohort](learner-cohort.md)); these sessions test what agents cannot:
whether a person unfamiliar with Patchground understands it and finds it worth doing.

Run each session with someone who has not worked on Patchground and has not seen its specs, the
reference solutions or this repository's discussions. One participant per session is enough to
close the gate; more is better. Record findings in [human-trial-findings.md](human-trial-findings.md).

## Facilitator rules

- Give the participant only the link to the README and the guide named below. Do not explain the
  product, demonstrate commands or hint at fixes. Answer only "what are you trying to do?".
- Watch and write down where they hesitate, what they misread and what they say aloud.
- If they are completely blocked for 5 minutes, you may help. Write down exactly what you said:
  that attempt becomes *assisted*, which is still useful evidence, never hidden.
- Do not record screens, file paths, machine names, emails or credentials. Summaries only.
- Stop at the challenge timebox. A failed or unfinished attempt is a valid result.

## Session A — first-time learner (about 45 minutes)

Participant brief (read it out as written):

> Patchground is a tool for practising real software work. Using only the README and
> `docs/first-session.md`, install it, pick a challenge from `examples/` that you have not seen,
> and try to solve it in your own editor. You may use any AI assistant you normally use. Think
> aloud. When you are done, or the timebox ends, run `pgnd submit` and read the report.

Suggested challenge: `pagination-last-page` (20 minutes) for a first contact, or any challenge
in the participant's stronger language. Afterwards ask:

1. In one sentence, what is Patchground for?
2. What was the most confusing moment, and what would have prevented it?
3. Did the ticket feel like real work? What felt artificial?
4. Did the final report tell you something you did not already know? Was anything in it unclear?
5. Would you use this again to practise? Why or why not?

## Session B — independent author (about 60 minutes)

Participant brief:

> Using only `docs/authoring.md`, create a small challenge of your own with `pgnd new`, based on a
> bug you have actually seen. Get `pgnd validate` to pass, then solve it once in a fresh session.
> Think aloud.

Afterwards ask:

1. Which step took longest, and why?
2. Was any validation failure message unclear? Quote it.
3. Did the scaffold help or get in the way?
4. Would you publish a challenge like this for others? What would stop you?

## Pass criteria

The gate passes when, for each session, at least one participant:

- completes the loop (A: install → start → check → submit → report; B: new → validate → solve)
  without facilitator help, **or** with help that led to a fix in the product or docs; and
- leaves no unresolved finding classified as a *blocker* in the findings file.

Every *blocker* is fixed before publication. *Friction* items are fixed or explicitly deferred with
a reason. Original observations are never rewritten; fixes are recorded beside them.
