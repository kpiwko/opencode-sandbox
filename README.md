# container image

An OpenCode sandbox workload image for the OpenShell runtime, built on **Red Hat
UBI9** from `registry.access.redhat.com`: a pinned OpenCode binary plus the pinned
OpenTelemetry plugin, at paths that a deny-by-default sandbox policy allows.

Published to `ghcr.io/kpiwko/opencode-sandbox` for `linux/amd64` and
`linux/arm64`. The consumer is the `openshell/opencode` stage in
[kpiwko/dotfiles](https://github.com/kpiwko/dotfiles), which pins one digest of
this image and ships the matching `opencode.json` and egress policy.

## Why a custom image

The published `ghcr.io/anomalyco/opencode` image ships OpenCode 1.x, which drops
the V2 `providers` block with a compatibility warning and then cannot resolve a
model. The OpenShell community base has no OpenCode at all. This image adds
OpenCode 2 to UBI9 and keeps the sandbox contract the consumer relies on: an
unprivileged `sandbox` user (uid/gid 998), a writable `/sandbox` home, and no
entrypoint.

UBI9 is used for both stages, so the image depends on RHEL content only, pinned by
digest — no Docker Hub, no distribution base image. `opencode --version` is
verified inside the build, which is possible exactly because every architecture is
built natively.

## What is pinned, and why

| Input | Pin | Why |
| --- | --- | --- |
| Runtime base | `ubi9/ubi` digest | A floating tag would move the workload under a policy that pins binary paths |
| Plugin stage | `ubi9/nodejs-24` digest | `npm install` for the plugin, at a pinned interpreter |
| OpenCode | version + per-arch SHA-256 | Downloaded from the release tarball; the checksum is what proves the artifact |
| OTEL plugin | version | Baked in, because the sandbox policy denies `registry.npmjs.org` |

Two constraints shape the build:

- **The plugin must load without network.** A `plugins` entry naming an npm
  package makes OpenCode run `npm install` at startup. Under a deny-by-default
  policy that fails, and telemetry silently disappears. The plugin is installed in
  a build stage and consumed as a directory.
- **No emulation.** OpenCode is a Bun binary and aborts under QEMU, so CI builds
  each architecture on a native runner (`ubuntu-24.04`, `ubuntu-24.04-arm`) with
  Podman/Buildah, then assembles one manifest with `podman manifest`. That is also
  why the upstream installer cannot be used: it executes the binary to verify it.

## Layout contract

These paths are referenced by the consumer's `opencode.json` and policy. Changing
them is a breaking change for that stage:

| Path / property | Meaning |
| --- | --- |
| `/usr/local/bin/opencode` | Binary, used as the egress policy's `binaries[].path` |
| `/usr/local/share/opencode/plugins/opencode-plugin-otel` | Plugin directory loaded by `plugins` |
| `/sandbox` | Home and workdir of uid/gid 998 (`sandbox`) |
| No `ENTRYPOINT` | OpenShell passes the main process as arguments; an inherited entrypoint would turn `sleep infinity` into a script path |

`/usr` is read-only in the sandbox policy; nothing here is written at runtime.

## Build and publish

CI publishes on every push to `main`, on a `v*` tag, and on manual dispatch:

```sh
gh workflow run build.yml --repo kpiwko/opencode-sandbox
```

The manifest job prints the digest to pin in its summary. Copy it into the
consumer's `create-sandbox.sh`; a floating tag would change the workload under a
policy that pins binary paths.

Local build of the native architecture:

```sh
podman build -t opencode-sandbox:local .
podman run --rm opencode-sandbox:local opencode --version
```

`build.sh` still exists for a local multi-arch build with `podman manifest`, but
publishing happens in CI: GHCR needs `write:packages`, which a developer `gh`
login does not carry.

## Checks

`scripts/check-inputs.py` asserts the invariants that are cheap to get wrong and
expensive to debug at runtime (digests pinned, checksums per architecture, plugin
path, cleared entrypoint, native CI). CI runs it before building, and the build
job smoke-tests the resulting image (`opencode --version`, uid 998, plugin file).
