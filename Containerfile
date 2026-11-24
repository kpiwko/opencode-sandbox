# OpenCode sandbox workload image, on Red Hat UBI9.
#
# Consumed by the `openshell/opencode` stage in kpiwko/dotfiles, which pins one
# digest of this image and ships the matching opencode.json and egress policy.
# The paths below are a contract with that stage; see README.md.
#
# Why a custom image at all: the published `ghcr.io/anomalyco/opencode` image
# ships OpenCode 1.x, which silently drops V2 configuration (`providers`), and the
# OpenShell community base ships no OpenCode at all.
#
# Both stages use RHEL content from registry.access.redhat.com, pinned by digest,
# so the image does not depend on Docker Hub.

# Build stage: only to install the OTEL plugin with its dependency tree.
FROM registry.access.redhat.com/ubi9/nodejs-24@sha256:0067c15398ece743e462637c8581b1b31027a7a2d3112e610ad700bde3b03f1b AS plugin

ARG OTEL_PLUGIN_VERSION=2.1.0

USER 0
WORKDIR /plugin

# The plugin is baked in rather than installed at runtime: the sandbox policy is
# deny-by-default and does not permit registry.npmjs.org, so a `plugins` entry
# naming an npm package fails to install and telemetry silently vanishes.
RUN set -eu; \
    npm pack "@devtheops/opencode-plugin-otel@${OTEL_PLUGIN_VERSION}" >/dev/null; \
    mkdir -p /out/otel; \
    tar -xzf ./*.tgz -C /out/otel --strip-components=1; \
    cd /out/otel; \
    npm install --omit=dev --no-audit --no-fund --ignore-scripts; \
    test -f /out/otel/dist/index.js

FROM registry.access.redhat.com/ubi9/ubi@sha256:6636b79fba9e5044360366f189333c30b5ce528efd92c40c68b074592b971fcd

ARG TARGETARCH
ARG OPENCODE_VERSION=2.4.1
ARG OPENCODE_SHA256_AMD64=9dbef68f231a311b56441c73c7bec01f6d87ebe44523ad14a7ba4716ff5c2031
ARG OPENCODE_SHA256_ARM64=9eb4567ff0fab90b6dac106f786652a0ec15d65e25ffbcbb106e5ed1cee4f4e2

# OpenCode comes from the release tarball rather than the upstream installer, so
# we can pin a checksum per architecture and never execute a foreign-arch binary
# during the build. The version check below runs unconditionally: CI builds each
# architecture natively, so it always can.

USER 0

# No package installs: ubi9/ubi already ships curl, tar, gzip, sha256sum, bash and
# useradd/groupadd. Its dnf repositories are subscription-gated, so installing
# anything would make the build depend on entitlements. `git` is the only thing
# missing, and this stage deliberately carries no repositories.

# Unprivileged default identity for native runs. OpenShell runs the workload as
# its own uid, so only the home path is a contract.
RUN set -eu; \
    groupadd --gid 998 sandbox; \
    useradd --uid 998 --gid 998 --home-dir /sandbox --shell /bin/bash --no-create-home sandbox; \
    install -d -o 998 -g 998 -m 0755 /sandbox

RUN set -eu; \
    case "${TARGETARCH:-$(uname -m)}" in \
        amd64|x86_64) target=linux-x64; sum="$OPENCODE_SHA256_AMD64" ;; \
        arm64|aarch64) target=linux-arm64; sum="$OPENCODE_SHA256_ARM64" ;; \
        *) echo "unsupported architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    tarball="/tmp/cli-${target}-${OPENCODE_VERSION}.tgz"; \
    curl -fsSL "https://registry.npmjs.org/@opencode/cli-${target}/-/cli-${target}-${OPENCODE_VERSION}.tgz" -o "$tarball"; \
    echo "${sum}  ${tarball}" | sha256sum -c -; \
    tar -xzf "$tarball" -C /tmp package/bin/opencode; \
    install -m 0755 /tmp/package/bin/opencode /usr/local/bin/opencode; \
    rm -rf /tmp/package "$tarball"; \
    installed="$(/usr/local/bin/opencode --version)"; \
    case "$installed" in \
        *"${OPENCODE_VERSION}"*) : ;; \
        *) echo "unexpected opencode version: $installed" >&2; exit 1 ;; \
    esac

# Read-only under /usr, which the filesystem policy allows. opencode.json points
# its `plugins` entry at this directory; a directory is loaded in place, unlike a
# package name, which triggers an npm install.
COPY --from=plugin /out/otel /usr/local/share/opencode/plugins/opencode-plugin-otel

USER sandbox
WORKDIR /sandbox

# UBI9 ships `/bin/bash` as the default shell but no ENTRYPOINT; clear it anyway so
# an inherited entrypoint can never turn the wrapper's `-- sleep infinity` into a
# script path.
ENTRYPOINT []
