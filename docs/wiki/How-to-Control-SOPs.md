**Goal:** keep standard operating procedures under document control: reviewed and signed before use, one version in force, every change recorded, and people trained on the current version.

**You need:** FoaMES Engineer or FoaMES Quality to write SOPs, and users holding the sign-off roles you choose.

## 1. Write the first revision

Open **Standard Operating Procedure** and fill in **SOP Code** (shared by all revisions), **Title**, **Category**, **Document Owner**, **Purpose**, **Scope**, **Responsibilities**, **Procedure** and **References**. Then:

- **Applies To**: a Machine, a Line or a Process Reference (an External Reference to an ERP operation or workstation). Leave empty for site-wide.
- **Approvals**: one row per sign-off, each a **Role** and a **Meaning** (Reviewed, Approved, Quality Approved).
- **Effective On**: empty to take effect on approval, or a date to allow training first.
- **Review Every (Months)**: 12 by default.
- **Requires Acknowledgement**, **Training Roles**, **Acknowledge Within (Days)**: who must read it, and how fast.

## 2. Review and sign

Press **Send for Review**; the content is now fixed. Each approval row is signed with **Sign** by a different person who holds its role, and not by the author. **Reject** sends it back to Draft and clears the signatures. The last signature makes it Approved, or Effective if its date has come.

## 3. Train

Users in the training roles press **Acknowledge** on the Effective revision; trainers use **Record Training**. The **SOP Training Matrix** report shows who is Current, Outdated or Missing, and who is overdue.

## 4. Change it later

Press **New Revision** on the Effective SOP. FoaMES copies it to a Draft numbered next; a **Change Summary** is required. When the new revision becomes Effective, the old one is Superseded. Use **Retire** to withdraw an SOP with no replacement, and **Record Periodic Review** when a review finds it still right.

The signatures are an audit trail, not a validated 21 CFR Part 11 electronic signature. Details: [docs/sops.md](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/sops.md).
