#!/usr/bin/env python3
"""Assert the image inputs that are cheap to break and costly to debug.

Each failure below is silent at build time and only shows up inside a sandbox: a
binary that cannot exec, a plugin that cannot be installed without network, a path
the egress policy then denies, or a main process that dies on startup.
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONTAINERFILE = (ROOT / "Containerfile").read_text()
WORKFLOW = (ROOT / ".github" / "workflows" / "build.yml").read_text()

UBI = "registry.access.redhat.com/ubi9/ubi@sha256:"
NODE = "registry.access.redhat.com/ubi9/nodejs-24@sha256:"
PLUGIN_DIR = "/usr/local/share/opencode/plugins/opencode-plugin-otel"

failures: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


# Both stages are RHEL content pinned by digest: a floating tag would move the
# workload under a consumer policy that pins binary paths.
check(UBI in CONTAINERFILE, "runtime base must be ubi9/ubi pinned by digest")
check(NODE in CONTAINERFILE, "plugin stage must be ubi9/nodejs-24 pinned by digest")
check(
    "registry.access.redhat.com/ubi9/ubi:" not in CONTAINERFILE,
    "runtime base must not use a floating tag",
)
check(
    "registry.access.redhat.com/ubi9/nodejs-24:" not in CONTAINERFILE,
    "plugin stage must not use a floating tag",
)

# OpenCode comes from the release tarball, so the checksum is the only proof of
# the artifact and must exist for every architecture we publish.
check("ARG OPENCODE_VERSION=" in CONTAINERFILE, "OpenCode version must be an explicit ARG")
check("ARG OPENCODE_SHA256_AMD64=" in CONTAINERFILE, "missing amd64 checksum")
check("ARG OPENCODE_SHA256_ARM64=" in CONTAINERFILE, "missing arm64 checksum")
check("sha256sum -c -" in CONTAINERFILE, "the downloaded tarball must be checksum-verified")
check("registry.npmjs.org/@opencode/cli-" in CONTAINERFILE, "OpenCode must come from the release tarball")
# The upstream installer executes the binary, which cannot run under emulation.
check("opencode.ai/v2/install" not in CONTAINERFILE, "must not use the install script")

# The plugin is consumed as a directory; the consumer config points at this path.
check("ARG OTEL_PLUGIN_VERSION=" in CONTAINERFILE, "plugin version must be pinned")
check("npm pack \"@devtheops/opencode-plugin-otel" in CONTAINERFILE, "plugin must be fetched and pinned")
check(f"COPY --from=plugin /out/otel {PLUGIN_DIR}" in CONTAINERFILE, "plugin copy target changed")

# OpenShell passes the main process as arguments, so an inherited entrypoint turns
# `sleep infinity` into a script path.
check("\nENTRYPOINT []\n" in CONTAINERFILE, "the entrypoint must be cleared")

# The consumer's policy pins uid-independent paths but the base contract keeps a
# fixed unprivileged identity and home.
check("--uid 998" in CONTAINERFILE, "sandbox uid must stay 998")
check("--home-dir /sandbox" in CONTAINERFILE, "sandbox home must stay /sandbox")
check("USER sandbox" in CONTAINERFILE, "image must run as the unprivileged sandbox user")
check("WORKDIR /sandbox" in CONTAINERFILE, "workdir must match the sandbox home")

# CI builds each architecture natively, so the version check stays on; it can only
# be disabled for a deliberate foreign-platform build.
check("ARG VERIFY_BINARY=1" in CONTAINERFILE, "the binary version check must be on by default")

check("ubuntu-24.04-arm" in WORKFLOW, "CI must build arm64 natively")
check("redhat-actions/buildah-build" in WORKFLOW, "CI must build with buildah")
check("podman manifest push --all" in WORKFLOW, "CI must publish one multi-arch manifest")
check("--digestfile" in WORKFLOW, "CI must surface the digest to pin")
check("packages: write" in WORKFLOW, "CI needs packages: write to push")
check("setup-qemu" not in WORKFLOW, "no emulation: both architectures build natively")

if failures:
    for failure in failures:
        print(f"FAIL: {failure}", file=sys.stderr)
    raise SystemExit(1)

print("ok: image inputs match the documented contract")
