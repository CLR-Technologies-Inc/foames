When FoaMES writes to another system (a Job Card time log in ERPNext, a confirmation in S/4HANA, a record in a Tulip Table), the hard part is not sending the request. It is knowing what to do when the answer is unclear: a timeout, a dropped connection, a 502. Did the write happen or not? Sending it again might double a confirmation or book stock twice. Not sending it might lose production data.

FoaMES answers that with an **outbox**. Every write is first a record (ERPNext Outbox, S4HANA Outbox, Insights Hub Outbox or MES Outbox), and the scheduler sends it later. The rules every adapter keeps are:

- **An idempotency key per business event**, such as the machine and the end of a roll-up window. Queuing the same key twice returns the first record, so a repeated job queues nothing new.
- **A check before any resend.** After an unclear answer, the posting is resent only if FoaMES can tell it did not happen. Depending on the system, that means an upsert that is safe to repeat, or a marker FoaMES wrote into a field it can search for (a *client reference*). If neither is available, the posting stops in **Unknown** with **Needs Check**, for a person to look and decide.
- **Strict order within a sequence group.** Postings for one Job Card or order operation go in order, and a failed one holds the rest, so no window is skipped or applied out of turn.
- **Retry for transient failures only.** Throttling, network errors and rejected logins are retried with exponential backoff. A validation or business error marks the posting **Failed** with the other system's message, for a person to fix and requeue.
- **Off until switched on.** Postings queue but are not sent until you enable them, and **Pause** holds them at any time without losing anything.

The **ERP Outbox Health** report shows each adapter's failed and waiting postings, the oldest unposted one and the last error, so integration problems are visible rather than silent.

The cost is latency: a posting goes out on the next scheduler run, not inside the machine event's transaction. For floor data that is the right trade. The floor stays fast when the ERP is slow, and every write leaves a record of what was sent, when, and what came back.

The framework is described in [docs/mes-adapters.md](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/mes-adapters.md#the-outbox) and in each vendor guide.
