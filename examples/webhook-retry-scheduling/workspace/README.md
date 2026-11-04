# Notification queue

`src/webhook_queue.py` owns delivery state. Its sender is injected, and every
drain receives integer milliseconds explicitly. `src/scripted_sender.py` provides
a deterministic fake for experiments: responses are consumed in order per ID,
and `calls` records what each send observed. Supply enough scripted responses
for the expected sends.

The existing queue supports one-shot success/permanent failure and due-item
selection. Extend it with the retry rules in the ticket. This is deliberately
not a durable or concurrent queue. Visible tests arrive under `tests/`; run
`pgnd check` inside your session.
