# Security

## Supported versions

DataSift 0.1.0 is unreleased. No released maintenance branch or security-support
window is currently declared. Fixes are reviewed against the current development
branch; do not infer support for a published version from the source version number.

## Reporting

Email [github@chooong.com](mailto:github@chooong.com) for confidential
vulnerability reports. Include the affected version or commit, impact and a
minimal synthetic reproducer. Do not include credentials, personal data or
production workbooks. Do not send exploit details through public issues.

The maintainers review reports through this mailbox. No response-time or
security-fix deadline is promised. Use the
[issue tracker](https://github.com/chooong-group/chooong.datasift/issues)
for non-sensitive bugs only.

## Processing untrusted files

Use caller-owned output directories and external process memory/time limits.
Streaming does not impose an absolute hostile-input RAM cap. See
[file safety](docs/reference/file-safety.md) and [limits](docs/reference/limits.md)
for implemented checks and their boundaries.
