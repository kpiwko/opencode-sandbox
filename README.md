# container image

An OpenCode sandbox workload image for the OpenShell runtime: the NVIDIA
community sandbox base plus a pinned OpenCode binary and the pinned OpenTelemetry
plugin, at paths that a deny-by-default sandbox policy allows.

Published to `ghcr.io/kpiwko/opencode-sandbox` for `linux/amd64` and
`linux/arm64`. The consumer is the `openshell/opencode` stage in
[kpiwko/dotfiles](https://github.com/kpiwko/dotfiles), which pins one digest of
this image and ships the matching `opencode.json` and egress policy.

## Why a custom image

The published `ghcr.io/anomalyco/opencode` image ships OpenCode 1.x, which drops
the V2 `providers` block with a compatibility warning and then cannot resolve a
model. The OpenShell community base has no OpenCode at all. This image adds
OpenCode 2 to that base and keeps the base's unprivileged `sandbox` user,
writable `/sandbox` home, and merged-`/usr` layout.

## What is pinned, and why

| Input | Pin | Why |
| --- | --- | --- |
| Base image | digest | A moving tag would change the workload under a policy that pins binary paths |
| OpenCode | version + per-arch SHA-256 | Downloaded from the release tarball; the checksum is what proves the artifact |
| OTEL plugin | version | Baked in, because the sandbox policy denies `registry.npmjs.org` |
| Build stage | `node:24-slim` | Used only to run `npm install` for the plugin |

Two constraints shape how this is built:

- **No binary execution while cross-building.** Bun, and therefore OpenCode,
  aborts under QEMU emulation, so the upstream installer (which executes the
  binary to verify it) cannot be used and `--version` cannot run on a
  cross-built architecture. The tarball checksum covers every architecture; the
  version check is opt-in via `VERIFY_BINARY=1` for a native build.
- **The plugin must load without network.** A `plugins` entry naming an npm
  package makes OpenCode run `npm install` at startup. Under a deny-by-default
  policy that fails and telemetry silently disappears, so the plugin is installed
  into a build stage and consumed as a directory.

## Layout contract

These paths are referenced by the consumer's `opencode.json` and policy. Changing
them is a breaking change for that stage:

| Path | Meaning |
| --- | --- |
| `/usr/local/bin/opencode` | Binary, used as the egress policy's `binaries[].path` |
| `/usr/local/share/opencode/plugins/opencode-plugin-otel` | Plugin directory loaded by `plugins` |
| `/sandbox` | Unprivileged user's home and workdir |

`/usr` is read-only in the sandbox policy; nothing here is written at runtime.

The base image's `ENTRYPOINT` is `/bin/bash`. This image clears it, because
OpenShell passes the sandbox's main process as plain arguments — with the
entrypoint inherited, `sleep infinity` becomes `bash sleep infinity` and bash
dies trying to run a script named `sleep`.

## Build and publish

CI publishes on every push to `main`, on a `v*` tag, and on manual dispatch:

```sh
gh workflow run build.yml --repo kpiwko/opencode-sandbox
```

The job prints the manifest digest in its summary. Copy that digest into the
consumer's `create-sandbox.sh` — a floating tag would change the workload under a
policy that pins binary paths.

Local build for inspection (publishing needs `write:packages`, which the CI
`GITHUB_TOKEN` has and a developer `gh` login does not):

```sh
./build.sh                    # both architectures, pushes to GHCR
PLATFORMS=linux/arm64 ./build.sh
```

## Checks

`scripts/check-inputs.py` asserts the invariants that are cheap to get wrong and
expensive to debug at runtime (checksum pinned per architecture, plugin path
present, entrypoint cleared, multi-arch CI). CI runs it before building.
