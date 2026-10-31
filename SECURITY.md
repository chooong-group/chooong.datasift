# Security

No package release has been published by this preparation. There is no historical
release-support promise. Security changes currently target the maintained `main`
branch; supported release lines will be stated here when releases exist.

Do not disclose exploitable vulnerabilities, credentials, personal workbooks or
sensitive output in public issues. If enabled, use GitHub's
[private vulnerability reporting](https://github.com/chooong-group/chooong.datasift/security/advisories/new).
If that facility is unavailable, request a private contact channel from the
maintainers without including exploit details. No unverified email address or
response-time guarantee is advertised.

XLSX files are ZIP archives containing XML. The reader rejects unsafe worksheet
paths, DTDs, malformed XML and selected invalid values, and has documented size
limits. These do not provide an absolute memory or time bound for hostile input.
Use an external process/RAM/time limit for untrusted workbooks; read
[resource limits](docs/errors.md). Macros and external links are not executed.

Public CI uses fresh GitHub-hosted runners with read-only repository permissions.
Publishing uses a separate, hard-disabled job and no permanent PyPI tokens.
Report accidental publishing capability or a bypass of the artifact gate as a
security concern. Never put real credentials in a reproducer.
