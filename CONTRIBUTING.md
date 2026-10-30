# Contributing to FoaMES

Thanks for helping build FoaMES. Bug reports, fixes, adapters and documentation are all welcome.

## Contributor License Agreement

FoaMES is licensed under the [Apache License 2.0](LICENSE). Before CLR Technologies Inc. ("CLR") can merge your first pull request, you need to agree to a Contributor License Agreement (CLA). You keep the copyright in your work. The CLA gives CLR and everyone who receives FoaMES a copyright license and a patent license for your contribution, on the same terms as the Apache Software Foundation's CLAs.

- **Contributing as an individual:** read the [Individual CLA](cla/ICLA.md).
- **Contributing for your employer:** your employer signs the [Corporate CLA](cla/CCLA.md) once and lists you on its Schedule A. Send the signed Corporate CLA to: `CLA contact address to be added by CLR`.

To sign, open your pull request. The CLA Assistant check posts a comment with a link. Follow it, sign in with GitHub and accept the agreement. Your GitHub account, the date and the agreement version are recorded, the `license/cla` check turns green, and you do not need to sign again for later pull requests. Every author of a commit in the pull request has to sign.

Every pull request also has a CLA checkbox in its description. Tick it to confirm that the CLA covers your contribution.

## Development setup

See [Installation](README.md#installation) and [Contributing](README.md#contributing) in the README for the bench setup and `pre-commit` hooks.

## Pull requests

- Keep each pull request to one change, and explain why it is needed.
- Add or update tests for behaviour changes. CI runs the tests on Frappe v15 and v16, with and without ERPNext.
- Credit any third-party code you include and keep its license notice with it.
