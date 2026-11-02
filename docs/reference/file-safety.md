# File safety and recovery

Inputs, mask and output destinations must be distinct. The CLI checks resolved
paths and same-file aliases, including `--explain`, and rejects symlinks and
commit/lock metadata destinations. Python `export` protects mask-file aliases;
native export protects input aliases. `--explain` is an independent write.

## Commit protocol

Scan and serialization finish into staged files, then each is flushed/fsynced.
Until that succeeds, prior destinations remain intact. A durable
`.OUTPUT.datasift-commit.json` journal binds each prepared stage to its SHA-256 checksum. Destinations
are renamed individually, with directory fsync on Unix, then the journal is
removed. These renames are **not** a shared atomic filesystem transaction.
Readers requiring both outputs must check that the commit journal is absent.
An interrupted commit can expose one new and one old destination; the journal
makes that state explicit. Preserve the journal and staged files, then run:

```text
from chooong.datasift import recover_export
recover_export(
    "matched.ndjson",
    journal_sha256=trusted_sha256,  # from the failed export error, stored separately
    rejected_output="rejected.ndjson",  # required if the commit includes rejects
)
```

Recovery requires a trusted SHA-256 of the complete journal and explicit caller
paths for **all** destinations. The native commit error includes
`journal_sha256=<hex>` after a journal was created. Store that value separately;
computing a hash from a possibly manipulated journal does not establish trust.
After an abrupt process crash with no independently preserved digest, automatic
recovery is refused: restore/re-export from the trusted input after inspecting
the incomplete output set. The old `recover_export(output)` call is incompatible.

Recovery checks manifest size/fields, exact destination bindings, reserved stage
names and byte hashes before committing. Journal destination/stage paths must
be absolute. Parent directories are canonicalized for comparison, including normal
and verbatim Windows path forms; final filenames must match exactly. Leaf paths
are not canonicalized or followed to authorize recovery. Regular files with exactly one link are
required for stages, journal, targets and locks. Symlinks, hardlinks and special
files are refused. Open directory capabilities pin the output directories;
private snapshots are hashed while copying from held file descriptors. Only
these snapshots are renamed, so replacing a stage path after checking cannot
substitute committed bytes. Source stages remain after recovery for inspection;
successful ordinary export removes its own stages.

Destination contents/identity, parent directories, locks and journal are checked
again before installation. A changed destination fails closed and the journal
remains. Completed destinations without a stage must already match the manifest.
A new export refuses an outstanding journal; repeating recovery after journal
removal fails. Stable `.OUTPUT.datasift.lock` sidecars serialize cooperative
writers and may remain after success.

Use caller-owned output directories protected against untrusted writers. Locks
are advisory; there is no portable compare-and-rename transaction against a
hostile process with the same filesystem authority. A final target symlink or
hardlink substitution is replaced as a directory entry, never followed to write
its linked victim. Multi-file commits can still be interrupted between installs;
readers must honor the journal. Private snapshots use mode 0700 directories on
Unix and inherited directory ACLs on Windows. Directory durability on Windows
is platform dependent and needs native testing. Inputs, mask and outputs must
be distinct; input aliases are refused.
`--explain` is a separate diagnostic write after result commit; it is not part
of the two-result commit protocol.

## Recovery call

The call above is a signature illustration: `trusted_sha256` must come from a
separately trusted record, not from the possibly modified journal. Python
`export` exposes commit errors containing this digest. The CLI redacts the
underlying error and does not expose it. Do not claim automatic recovery after a
crash that lost the independently preserved digest.

[Exporting](../guides/exporting.md) defines record formats;
[Python API](../api/python.md) defines exact callable signatures.
