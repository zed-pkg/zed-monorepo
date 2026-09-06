# Security policy

## Supported versions

Security fixes are developed on the default branch and included in the next
appropriate tagged release. Historical documentation snapshots and unmaintained
branches are not independently patched.

## Reporting a vulnerability

Do not open a public issue containing exploit details, credentials, private
repository names, customer data, or unredacted logs.

1. Open the **Security** tab of the affected zed-pkg repository and use
   **Report a vulnerability** when private vulnerability reporting is offered.
2. For a cross-repository problem, start with the repository that owns the
   vulnerable runtime or contract. Include the other affected repositories in
   the private report.
3. When no private reporting entry is available, open a minimal public issue
   asking maintainers for a private contact channel. Do not include the
   vulnerability details in that issue.

A useful private report includes affected versions or commits, impact,
reproduction steps, expected and observed behavior, and any proposed fix.
Remove bearer tokens, signed URLs, personal data, and unrelated secrets from
all evidence.

## Coordinated disclosure

Please allow maintainers to reproduce, patch, test dependent repositories, and
prepare release guidance before public disclosure. The exact timeline depends
on severity, exploitability, and the number of affected packages or deployed
services.

## Scope

Security boundaries described in this repository are part of the supported
architecture contract, including artifact digest verification, credential
isolation, redirect refusal, deterministic release planning, browser Content
Security Policy, FFI ownership, and private/public repository-data separation.
