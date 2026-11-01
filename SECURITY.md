# Security

Security fixes target the maintained `main` branch.

Do not disclose exploitable vulnerabilities, credentials, personal workbooks or
sensitive output in public issues. If enabled, use GitHub's
[private vulnerability reporting](https://github.com/chooong-group/chooong.datasift/security/advisories/new).
If that facility is unavailable, request a private contact channel from the
maintainers without including exploit details.

XLSX files contain ZIP/XML data. Apply external process, memory and time limits
for untrusted input; parser limits are not an absolute resource bound. See
[Limits & Errors](docs/limits.md). Macros and external links are not executed.
