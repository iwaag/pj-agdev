You are deciding one thing: is the conversation named above stuck, or is it
waiting for a good reason? Everything you need is above. You do not act,
post or fix anything; you only answer.

- `stall` — nothing will move unless somebody does something: a request
  that was closed (✔) while its work was still going on and nobody meant to
  end it; a worker that went silent with nothing saying it is still busy.
- `legit` — the wait is intended: the ✔ was a deliberate close (the work was
  withdrawn, replaced or answered "nothing to do"), or a long job was
  started and said how long it takes, or a human was asked a question and
  has not answered yet.
- `unclear` — the messages do not let you tell. Say what is missing.

A ✔ does not stop anything, so the two can look alike: work that waits for
somebody's decision, with its conversation ✔. Look at the request's own
conversation, where that decision is asked for. If the question has been put
to the person who decides and they have not answered, the next move is
theirs and they know it: `legit`. If nobody has told them, `stall`.

Judge from what the messages say, not from how long it has been. Quote the
message ids you relied on.

Write your answer as JSON into `result.json` in the working directory, and
nothing else is needed:

    {"verdict": "stall", "evidence": "#8292 posted the mission; #8293 is the ✔ four seconds later with no word of closing; autolab answered in #8322 after it."}
