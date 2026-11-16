# Contributing to FoaMES

Thanks for helping build FoaMES. Bug reports, fixes, adapters and documentation are all welcome.

## Contributor License Agreement

FoaMES is licensed under the [Apache License 2.0](LICENSE). Before CLR Technologies Inc. ("CLR") can merge your first pull request, you need to agree to a Contributor License Agreement (CLA). You keep the copyright in your work. The CLA gives CLR and everyone who receives FoaMES a copyright license and a patent license for your contribution, on the same terms as the Apache Software Foundation's CLAs.

- **Contributing as an individual:** read the [Individual CLA](cla/ICLA.md). The copy you sign through CLA Assistant is published at https://gist.github.com/CLRTechDev/b5b61defe307dd1d0f2f3173bb9ef36b.
- **Contributing for your employer:** your employer signs the [Corporate CLA](cla/CCLA.md) once and lists you on its Schedule A. Send the signed Corporate CLA to dev@clrtechnologies.co.

To sign, open your pull request. The CLA Assistant check posts a comment with a link. Follow it, sign in with GitHub and accept the agreement. Your GitHub account, the date and the agreement version are recorded, the `license/cla` check turns green, and you do not need to sign again for later pull requests. Every author of a commit in the pull request has to sign.

Commits authored by the `claude` GitHub account are AI-assisted work by CLR staff, made with Anthropic's Claude Code. CLR owns that work under its agreement with Anthropic, so the `claude` account is on the CLA Assistant allowlist and does not sign the CLA. The CLR staff member who opens the pull request is responsible for it.

Every pull request also has a CLA checkbox in its description. Tick it to confirm that the CLA covers your contribution.

## Development setup

See [Installation](README.md#installation) and [Contributing](README.md#contributing) in the README for the bench setup and `pre-commit` hooks.

## Pull requests

- Keep each pull request to one change, and explain why it is needed.
- Add or update tests for behaviour changes. CI runs the tests on Frappe v15 and v16, with and without an optional ERP app installed.
- Start every new source file with the license header (the `license-headers` pre-commit hook checks it):

  ```python
  # Copyright (c) 2026 CLR Technologies Inc. and contributors
  # SPDX-License-Identifier: Apache-2.0
  ```

  Frappe's DocType generator writes a header that points at `license.txt`; replace it with this one.
- Add a changelog fragment under [`changelog.d/`](changelog.d/README.md) for a user-facing change, for example `changelog.d/81.added.md`. Do not edit `CHANGELOG.md` or the version: both change only at release time ([docs/versioning.md](docs/versioning.md)).
- Credit any third-party code you include and keep its license notice with it. Only code under a license compatible with Apache-2.0 can be included, and GPL code (ERPNext included) cannot be copied into FoaMES. See [docs/licensing.md](docs/licensing.md).

## Keeping private information out

FoaMES is public, so every commit, pull request title and description is public too.

- Your own name, email and GitHub account on the commits you author are your signature and are public by design. If you would rather not publish your email, use your GitHub noreply address (`<id>+<login>@users.noreply.github.com`) with `git config user.email <address>`.
- Do not add other people's personal details. An email address in new content passes when it belongs to an author of the change (including `Co-authored-by` and `Signed-off-by` trailers), is already in the repository, is a placeholder on a documentation domain such as `example.com`, or sits in an attribution or reference file (NOTICE, AUTHORS, CITATION, `.bib`). Credit and cite people there. Anything else is flagged, with the file and line but not the address.
- Never commit secrets, site configuration (`site_config.json`), `.env` files, keys or certificates. `.gitignore` covers the usual names, GitHub push protection blocks known secret formats, and gitleaks runs locally and in CI.
- Tenants, providers and estates are referred to generically, never by a company's name. CI checks files, commit messages and pull request text against a private word list.
- Run `pre-commit install` once. It installs the license, name, personal-details and gitleaks checks for both commits and commit messages.

Report a security problem privately, as described in [SECURITY.md](SECURITY.md).
