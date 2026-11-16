# Equipment commissioning

FoaMES tracks the commissioning of new or rebuilt equipment from the factory acceptance test to the handover to operations and maintenance. It follows common commissioning practice for process and packaging plants: tests with signed steps, loop checks from field device to control system, a categorised punch list, and a handover that cannot happen while anything still blocks it.

Commissioning ends at handover. Qualification (IQ, OQ, PQ) and process validation follow it and are not part of this module; the package links to the qualification record and calls a hook at handover so a validation module can start from there (see [Extending](#extending)).

## The records

| DocType | What it is |
| --- | --- |
| **Commissioning Package** | One commissioning job: the equipment in scope (by equipment tag, optionally linked to a FoaMES Machine), the tests it must pass, its progress, its blockers and its handover. |
| **Commissioning Checklist Template** | A reusable list of checks for one test type and, optionally, one equipment type. |
| **Commissioning Test** | One FAT, Mechanical Completion, Pre-Commissioning, SAT, Functional Test or Performance Test, with its steps and sign-offs. |
| **Loop Check** | One instrument or signal checked from the field device to the control system, at points across its range or in each state. |
| **Punch Item** | A deficiency found along the way, with its category, owner, due date and close-out. |

All of them are in the **FoaMES Commissioning** workspace, with the **Punch List** and **Commissioning Status** reports and four number cards.

## The flow

1. **Create a package.** Give it a title, the line, the commissioning lead and the planned handover date, and list the equipment in scope. Each piece of equipment has a unique tag (for example `FIL-201` for a filler); link it to its Machine when it has one. A machine that is disabled while it is being commissioned is enabled at handover when **Enable Machines on Handover** is set (the default), so it joins OEE only once it is accepted.
2. **Choose the required tests.** By default a package needs at least one passed FAT, Mechanical Completion and SAT. Pre-Commissioning, Functional Test, Performance Test and loop checks can be required too.
3. **Run the tests.** Create a Commissioning Test for each test, either from a template (its checks are copied in) or by entering the steps. For each step record the result:
   - a **Check** or **Text** step takes Pass, Fail or N/A from the tester;
   - a **Value** step takes a measured value and is judged against its low and high limits (either may be blank). A reading outside the limits fails the step.
   A test fails as soon as any step fails. When every step passed or does not apply, the test waits for **Performed By**, and for **Witnessed By** when the test needs a witness (a FAT witnessed by the customer, for example), and then passes.
4. **Keep the sequence.** With **Enforce Test Sequence** (the default), a test cannot start while a test of an earlier stage on the same equipment has not passed: SAT waits for FAT and Mechanical Completion, for example. A test with no equipment tag covers the whole package and is held by, and holds, the tests of every piece of equipment.
5. **Check the loops.** A Loop Check is filled with the usual points when it is created: 0, 25, 50, 75 and 100 percent of span for an analog loop, On and Off for a digital one. Enter the calibrated range, the tolerance (percent of span, 1 by default) and, for each point, the as-found reading and, if the loop was adjusted, the as-left reading. The point passes when the deciding reading is within tolerance of the expected value. The loop passes when every point passes and the technician signs it in **Checked By**.
6. **Clear the punch list.** A failed test step raises a punch item of the step's category, once, linked back to the step. A failed loop check raises one punch item of the loop's category (A by default). People raise punch items by hand too, Operators included.
7. **Accept and hand over.** Name who accepts for operations and who accepts for maintenance. Once nothing else blocks the handover, each of them presses **Accept for operations** or **Accept for maintenance**. Then an Engineer or Supervisor presses **Hand Over**.

## Punch item categories

| Category | Meaning | Blocks handover |
| --- | --- | --- |
| A | Safety, or the equipment cannot start or run as intended | Always, while open. It cannot be deferred. |
| B | Must be fixed, but the equipment can run | While open, unless it is **deferred** with an owner and a due date. A deferred item goes over with the equipment and stays on the punch list. |
| C | Cosmetic or minor | Never. |

A punch item moves from Open to Ready for Verification to Closed (or Cancelled). Closing needs the action taken and records who verified it and when. A closed or cancelled item cannot be reopened; raise a new one.

## What blocks handover

The package's **Handover Blockers** section lists everything that holds it back, and the package's status follows from it: Planning, In Progress, Ready for Handover, then Handed Over (or Cancelled). A package is blocked by:

- no equipment in scope;
- a required test type that has no passed test;
- any test or loop check that has not passed (cancelled ones are ignored);
- an open category A punch item, or an open category B item that is not deferred with an owner and a due date;
- no named acceptor for operations or for maintenance;
- anything another app reports through the readiness hook.

Hand Over also needs both acceptances. After handover the package's tests and loop checks are frozen, but punch items can still be raised on it.

## Suggestions

`foames.foames_commissioning.tasks.check_commissioning` runs daily and raises an **Agent Suggestion** (category Commissioning):

- for each open punch item past its due date: severity Critical for category A, Warning for B, Info for C;
- for each package past its planned handover date that is not handed over: severity Warning, with the number of blockers.

Each item raises once per due date. Closing or cancelling a punch item marks its open suggestions Done.

## Reports

- **Punch List**: punch items by category, worst first, with whether each blocks the handover, whether it is overdue, and how long it has been open. Filter by package, category, owner or equipment.
- **Commissioning Status**: one row per package with its progress, open punch items by category, blockers and whether it is late.

## API

- `foames.foames_commissioning.doctype.commissioning_package.commissioning_package.get_readiness(package)`: whether the package is ready and what blocks it.
- `foames.foames_commissioning.doctype.commissioning_package.commissioning_package.get_handover_dossier(package)`: the package, its readiness, every test with its steps, every loop check with its points and every punch item, as one JSON structure for a handover certificate, an agent or the qualification that follows.
- `accept` and `hand_over` are whitelisted methods of the Commissioning Package document (`frappe.client` `run_doc_method`, or `frm.call` in the desk).

## Extending

Two hooks in `hooks.py` let another app take part without changing FoaMES:

```python
# Each returns a list of blocker dicts: {"kind": ..., "reference": ..., "message": ...}
foames_commissioning_readiness_checks = ["myapp.qualification.blockers"]  # (package)
# Called after a package is handed over
foames_commissioning_handed_over = ["myapp.qualification.on_handover"]  # (package)
```

FoaMES Validation uses the second hook: at handover it opens a draft IQ execution for each machine in the package that has an approved IQ protocol (or raises a suggestion to write one) and writes it back to the package's **Qualification Type** and **Qualification Record** fields; see [validation.md](validation.md#from-commissioning). Another qualification app can register the same hook. The commissioning arithmetic (step and loop evaluation, the test sequence, punch item rules, readiness) is pure Python in `foames/foames_commissioning/commissioning.py`.
