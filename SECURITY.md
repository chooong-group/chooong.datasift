# Security

## Supported versions

DataSift 0.1.0 is unreleased. No released maintenance branch or security-support
window is currently declared. Fixes are reviewed against the current development
branch; do not infer support for a published version from the source version number.

## Reporting

The repository's [issue tracker](https://github.com/chooong-group/chooong.datasift/issues)
is available to users with repository access. Use it only for reports that contain
no confidential details, credentials or personal data. Include a minimal synthetic
reproducer and the affected commit/version.

No private reporting address or private vulnerability-reporting channel is
currently documented. Do not submit sensitive exploit details through public
issues or include them in uploaded workbooks. A private reporting route must be
established by the maintainers before sharing confidential material; this policy
does not invent a contact address or response-time commitment.

## Processing untrusted files

Use caller-owned output directories and external process memory/time limits.
Streaming does not impose an absolute hostile-input RAM cap. See
[file safety](docs/reference/file-safety.md) and [limits](docs/reference/limits.md)
for implemented checks and their boundaries.
