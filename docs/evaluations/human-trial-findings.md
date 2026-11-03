# Human acceptance findings

Record each session here using the template below. Keep entries free of names, emails, machine
names, file paths and credentials. Use a participant label such as `H1`.

## Status

No human session has been recorded yet. Version 0.1.0 and the website are now public, but
independent-human acceptance remains unverified. The owner confirmed that learner and author trials
remain pending; publication is not evidence that this gate passed. See the
[human-acceptance task](../work/human-acceptance.md) for the next action.

The later [guide/onboarding synthetic trials](agent-guide-smoke.md) completed learner and author
workflows and found minor guidance issues. Those agents are not participants in this record; no
human session or human acceptance is claimed.

## Template

```text
Session:            A (learner) | B (author)
Participant:        H<n>; role/experience in one line (e.g. "backend dev, 4 years Python")
Date:               YYYY-MM-DD
Product commit:     <git rev-parse --short HEAD>
Platform:           macOS | Linux | Windows (WSL2); Docker Desktop | Docker Engine | Podman
Challenge:          <id> (or the authored challenge's id for session B)
Outcome:            completed unassisted | completed assisted | not completed
Time used:          <minutes> of <timebox>
Assistance given:   none | exact words of every intervention
AI assistant used:  none | which one (participant's own)

Observations (in order, one line each):
- [blocker|friction|positive] what happened, quoted where possible

Answers to the debrief questions:
1. ...

Follow-up:
- finding -> fix commit or "deferred: reason"
```
