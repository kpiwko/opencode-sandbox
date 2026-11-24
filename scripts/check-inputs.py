#!/usr/bin/env python3
"""Assert the image inputs that are cheap to break and costly to debug.

These checks exist because each failure below is silent at build time and only
shows up inside a sandbox: a binary that cannot exec, a plugin that cannot be
installed without network, a mismatched path the policy then denies.
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONTAINERFILE = (ROOT / "Containerfile").read_text()
BUILD = (ROOT / "build.sh").read_text()
WORKFLOW = (ROOT / ".github" / "workflows" / "build.yml").read_text()

BASE = "ghcr.io/nvidia/openshell-community/sandboxes/base@sha256:"
PLUGIN_DIR = "/usr/local/share/opencode/plugins/opencode-plugin-otel"

failures: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


# The base must be pinned by digest: a floating tag would move the workload under
# a consumer policy that pins binary paths.
check(BASE in CONTAINERFILE, "Containerfile must use the OpenShell base by digest")
check(
    "FROM ghcr.io/nvidia/openshell-community/sandboxes/base:" not in CONTAINERFILE,
    "Containerfile must not use a floating base tag",
)

# OpenCode comes from the release tarball, so the checksum is the only proof of
# the artifact; it has to exist for every architecture we publish.
check("ARG OPENCODE_VERSION=" in CONTAINERFILE, "OpenCode version must be an explicit ARG")
check("ARG OPENCODE_SHA256_AMD64=" in CONTAINERFILE, "missing amd64 checksum")
check("ARG OPENCODE_SHA256_ARM64=" in CONTAINERFILE, "missing arm64 checksum")
check("sha256sum -c -" in CONTAINERFILE, "the downloaded tarball must be checksum-verified")
check("registry.npmjs.org/@opencode/cli-" in CONTAINERFILE, "OpenCode must come from the release tarball")
# The upstream installer executes the binary; Bun aborts under QEMU, so using it
# would make a cross-build impossible.
check("opencode.ai/v2/install" not in CONTAINERFILE, "must not use the install script")

# The plugin is consumed as a directory; the consumer config points at this path.
check("FROM node:24-slim AS otel-plugin" in CONTAINERFILE, "plugin build stage missing")
check("ARG OTEL_PLUGIN_VERSION=" in CONTAINERFILE, "plugin version must be pinned")
check(f"COPY --from=otel-plugin /out/otel {PLUGIN_DIR}" in CONTAINERFILE, "plugin copy target changed")

# OpenShell passes the main process as arguments, so an inherited bash entrypoint
# turns `sleep infinity` into a script path.
check("\nENTRYPOINT []\n" in CONTAINERFILE, "the base image entrypoint must be cleared")

check("USER sandbox" in CONTAINERFILE, "image must run as the unprivileged sandbox user")
check("WORKDIR /sandbox" in CONTAINERFILE, "workdir must match the sandbox home")

# The version check executes Bun, so it may only run natively.
check("ARG VERIFY_BINARY=0" in CONTAINERFILE, "the binary version check must be opt-in")
check('--build-arg "VERIFY_BINARY=$verify"' in BUILD, "build.sh must enable the check only natively")

check("platforms: linux/amd64,linux/arm64" in WORKFLOW, "CI must publish both architectures")
check("steps.build.outputs.digest" in WORKFLOW, "CI must surface the digest to pin")
check("packages: write" in WORKFLOW, "CI needs packages: write to push")

if failures:
    for failure in failures:
        print(f"FAIL: {failure}", file=sys.stderr)
    raise SystemExit(1)

print("ok: image inputs match the documented contract")
