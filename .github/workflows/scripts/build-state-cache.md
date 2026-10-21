# Shared tools/toolchain state cache

The release workflow caches the complete host and current toolchain build and
staging directories. Downloads, ccache, target packages, `.config`, and `tmp`
are excluded from the payload.

## Identity and native Make

Prepare expands each selected profile with `make defconfig` and queries native
Make for enabled tools, compiler components, configure arguments, build recipes,
and the four state directories. Equal inputs form one scheduling group.
The workflow passes `CONFIG_BUILDBOT=y` only to the native tools/toolchain Make
invocations, rather than forcing it into `.config`. Its native version check
remains enabled without changing Kconfig defaults for `ALL_NONSHARED`,
`ALL_KMODS`, `SDK`, `IB`, or feed applications. Package selection remains driven
by the profile, target defaults, and Kconfig dependencies. Unselected packages
must not become `m` merely because this is CI; `m` also participates in compilation.
Profile names, feed revisions, and the whole firmware config are not identity
fields. A normal package change can reuse state; a package that changes an
actual host tool or compiler recipe changes the group.

Each group's producer rechecks every member on its own runner. Scheduling is
only a hint: restore also requires the native build inputs and absolute build
path to match. All jobs use `ubuntu-latest`. Runner image revisions, operating
system versions, kernel versions, package inventories, and ambient environment
inventories are not cache identity or handoff compatibility fields. Dependencies
installed on the runner support bootstrap; they do not version the cached build.
The host LLVM BPF option additionally needs both `clang` and `llvm` for package
compilation (`opt`, `llc`, `llvm-dis`, and `llvm-strip`).
Input field hashes are printed and plans are retained in toolchain diagnostics.
A consumer with different native inputs builds independently and does not retire
the producer's valid cache. Cached host executables may still use system dynamic
libraries; execution/link smoke tests and the native build check them in practice,
with one clean retry after a reused build fails.

Shared build helpers, scripts, tools headers, and kernel sources have a content
guard because native per-component checks do not cover all changes to them.
Other source content is recorded separately. Restore retains timestamps only
for unchanged sources. Changed sources remain subject to native Make checks.
POSIX tar and zstd preserve nanosecond mtimes, permissions, links, and real
completion stamps. Stamps are never fabricated.

Native `include/download.mk` makes each `.prepared` stamp depend on its source
archive in `dl`. Restoring build directories without those archives previously
caused fresh downloads to invalidate otherwise usable tools and toolchains.
The producer now records only hashes, modes, and timestamps of its downloaded
source archives in the manifest. Consumers and warm producers run native
`tools/download` and `toolchain/download`, verify the resulting file contents,
and retain timestamps only for identical downloads before checking compilation.
No download contents enter cache or handoff payloads, and no archive names or
package versions are maintained in the workflow. Different contents or modes
retain their current timestamps and remain subject to native Make checks.
Download failures stop the build without retiring the valid restored generation.

Every restore checks inputs, archive checksum, paths, metadata, native stamps,
host tools, and cross-compiler C/C++ linking and ELF architecture. Producers and
consumers still execute `tools/compile` and `toolchain/compile`, with native
`CONFIG_AUTOREBUILD` and `CONFIG_BUILDBOT` checks enabled. These phases consistently
use `SOURCE_DATE_EPOCH=0 REVISION=ci-tools CONFIG_BUILDBOT=y`; firmware uses its
normal values.
Only a failure after reuse permits one clean toolchain retry.
When native completion stamps change after reuse, their added, removed, and
changed paths are reported so a successful restore is not mistaken for a fully
unchanged build.

## One producer, independent firmware builds

One tools job produces each group. Groups run in parallel. A verified state
archive is handed off once per group in a temporary artifact; firmware jobs
restore independent copies with their own final configs. Two compatible
Linksys profiles therefore share one producer and one persistent generation.
`force_rebuild` forces each producer once; its consumers can use that new state.

The cache publisher matrix uses `max-parallel: 1`. Firmware starts after its
publication attempts, so toolchain saving precedes firmware failures. Failed
groups or publishers do not skip otherwise valid firmware jobs; missing
handoffs fall back to compatible cache or a cold build. Firmware/package failures
alone do not retire toolchains.

Artifacts contain sealed tar payloads, with hidden paths explicitly enabled
and outer compression disabled. Payload names contain group and producer
attempt. Small receipts retain the actual artifact ID and generation key for
seven days. Failed-job reruns use that producer attempt, even when the rerun's
attempt differs; if the payload was cleaned or expired, the recorded exact
cache generation is tried first and validated again.

Payload artifacts have one-day retention and are explicitly removed after
publishers and consumers finish. This is transient artifact storage, separate
from the cache quota and subject to the account's artifact limits. Upload errors
or quota exhaustion cause normal build fallback.

## Serialized publication and retirement

Only the default branch writes persistent state. `owrt-state-v4` keys contain
the full compatibility fingerprint, run ID, attempt, scheduling group, and a
retention scope:
`owrt-state-v4-<fingerprint>-<run>-<attempt>-<group>-scope-<scope>`.
Fingerprint restore prefixes select previous generations with the same native
inputs. Retention scope is the hash of native Make's `BOARD` and `SUBTARGET`;
it is stored outside compatibility inputs and never authorizes a restore.
For example, x86/64 has one retention scope and both current Linksys profiles
share mvebu/cortexa9. Compiler versions, common-source changes, and package
selection do not create new retention scopes.

There is no custom snapshot-size, repository-size, or group-count admission
limit. The configured 10GB repository quota and capacity/idle eviction belong
to GitHub. No other group is deleted to reserve space before an upload.

Replacement uploads precede retirement within the same retention scope.
The publisher
must confirm the exact key/ref and a visible cache ID through the API; a save
action's success alone is insufficient. Confirmation failure retains previous
generations. Once confirmed, the scope keeps one persistent generation even when
common-source or compiler changes create a different scheduling group. The
prepare job's complete group plan protects other groups required by this run;
if several incompatible groups share a native target, each active group retains
its own generation. Other scopes, unrelated keys, and other refs are left alone.
A replacement temporarily overlaps its previous
generation; failed uploads or failed retirement can leave extra entries until
the next successful publication. GitHub eviction can still cause cache misses.

An unchanged warm restore reuses its existing generation without another
persistent upload. Small native rebuilds produce a replacement through the same
snapshot and publication path.

Producers and consumers only record rejected exact generation keys. The final
serial job deduplicates reports, resolves current IDs by exact key/ref, and
retires them after publication. DELETE 404 is idempotent. Input incompatibility
and artifact transport corruption alone do not prove the persistent copy is
bad. No reader runs global cache garbage collection.

The workflow retains its existing global concurrency group to exclude old and
new workflow versions. `cancel-in-progress: false` and `queue: max` preserve
queued runs without adding a second lock inside that group.

Run local regression checks with:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 .github/workflows/scripts/test_build_state_cache.py -v
```

Local tests cover native input selection, cross-profile grouping, source
and download timestamps, native download dependencies, archive safety,
compiler aliases, bounded retry, unrestricted capacity admission,
confirmation-before-retirement, failed-job reruns, and deduplicated retirement.
Runner cold/hot acceptance must inspect real component build logs and completion
stamp differences. Most tools and the cross toolchain must be reused; a small
number of native tool rebuilds is acceptable. A cache-hit message alone is not
evidence of avoided builds. Do not add tool-specific exceptions just to obtain
zero stamp changes or weaken restore validation to avoid native rebuilds.

### Temporary unscoped-v4 migration (2026-10-21)

Older v4 keys lack the retention scope. They remain restorable using their
original strict fingerprint and group checks. A warm unchanged snapshot receives
a scoped key and matching metadata without repacking its payload or altering
its native inputs, source timestamps, or completion stamps.

After a scoped replacement is visible, an old group is retired only when its
origin run's exact key/ref receipt proves that every member profile is covered
by the new producer. Missing or expired ownership metadata preserves the cache;
unknown caches must not be classified by archive size or hash guessing.
Same-group retirement continues to work without historical metadata.

Removal criterion: after the default branch has successfully published scoped
generations for all supported target groups and the live cache inventory has no
unscoped v4 keys, remove `legacy_retirements`, its optional origin-run receipt
lookup parameters, unscoped key/metadata acceptance, and the metadata-only
snapshot retagging branch together. No production build-source migration is
involved.

## Independent target releases

Release publication uses a serial target matrix with `fail-fast: false`.
Its job condition permits successful artifacts to be published even if another
build target fails. Each publisher selects only the unexpired `firmware-<target>`
artifact; a missing artifact leaves that target's existing release assets alone.
Download/API failures remain visible failures for that publisher and do not
stop the other target publishers.

All firmware images and metadata carry a `<target>--` filename prefix.
Each target has its own `sha256sums-<target>.txt`. Nightly remains one release,
with the latest successful set for each target. Once all new target assets are
confirmed by remote name, size, uploaded state, and SHA-256 digest, obsolete
filenames within that target's namespace are removed, including older dates.
Old unprefixed assets are migrated using their existing per-target checksum
indexes; filenames also referenced by another target are protected.
An unreadable historical checksum index only disables legacy unprefixed
retirement; it does not block publication or namespaced retirement for a target.
The obsolete aggregate `sha256sums-all.txt` is removed because it cannot
describe a nightly containing independently updated targets.

The release service cannot atomically replace several files. If an upload
fails, retirement is skipped and previous differently named firmware files
are kept; overwriting an identically named file is still subject to GitHub's
delete/upload behavior. A later successful publication cleans up that target.
Tagged releases do not run nightly retirement. Local release checks are:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 .github/workflows/scripts/test_release_assets.py -v
```
