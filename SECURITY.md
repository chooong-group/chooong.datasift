# Security

Security fixes target the maintained `main` branch.

This project does not offer a private vulnerability reporting channel.
Do not post vulnerability details, credentials or sensitive workbooks in public issues.

XLSX files contain ZIP/XML data. Apply external process, memory and time limits
for untrusted input; parser limits are not an absolute resource bound. See
[Limits & Errors](docs/limits.md). Macros and external links are not executed.
