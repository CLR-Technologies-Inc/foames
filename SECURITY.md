# Security policy

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub: open the repository's **Security** tab and choose **Report a vulnerability**. Do not open a public issue, pull request or discussion for a suspected vulnerability.

Include what you found, the affected version or commit, and the steps to reproduce it. We aim to acknowledge a report within five working days and to agree a disclosure date with you once a fix is ready.

## Scope

In scope: the FoaMES Frappe app in this repository (`foames/`), its adapters, bridges (`bridges/`), the MCP server, the workflows in `.github/`, and the dev bench in `docker/`.

Out of scope: Frappe, ERPNext and other third-party software (report those to their maintainers), and sites you run yourself, whose configuration is your responsibility.

## Supported versions

Security fixes go to the latest release and to `main`.

## Secrets found in the repository

If you find a credential or other private information in this repository or its history, report it the same private way rather than in a public issue.
