# The plugin's image. It runs beside a sidecar in the deployment's cluster, and
# reaches nothing but that sidecar and Polymarket US's public gateway.
#
# Built on the base image for the SDK this plugin pins: Python and
# open-meridian, the same version as pyproject.toml's, already installed. So
# the image's own layer is this plugin, and an upload sends only that. Move the
# two together when moving to a new SDK.
#
# BASE is for building against a base made locally rather than a released one:
# `make image` builds plugin-python:<version>-local from the sibling
# meridian-python while that version is not published.
# The release by its tag and its digest, the image exactly; move both together.
ARG BASE=ghcr.io/open-meridian/plugin-python:0.33.0@sha256:c95f1a03d8a832b24b4ac3bd8b9dbddcb6eaa22263acbd92da6f91c0c0fe39c6
FROM ${BASE}
WORKDIR /plugin
# Installed from a mount rather than copied, so the image holds the installed
# package and no source beside it.
RUN --mount=type=bind,target=/tmp/src,rw pip install --no-cache-dir /tmp/src
# The vendor's documentation (contract v25): the declaration names docs/,
# relative to where the plugin runs, /plugin, and `meridian-declaration`
# reads it there when `meridian plugin upload` prints the declaration.
COPY docs/ docs/
USER 65532
CMD ["polymarket-us"]
