#!/bin/bash
set -ex
MYORG=${MYORG:-holdenk}
VERSION=${VERSION:-0.0.31}
BUILDX_CMD=${BUILDX_CMD:-push}
PLATFORM=${PLATFORM:-linux/amd64,linux/arm64}
image="${MYORG}/moonshine4homeassistant:${VERSION}"
docker buildx build --platform="${PLATFORM}" -t "${image}" --build-arg VERSION=moonshine-${VERSION} -f "${dockerfile}" "--${BUILDX_CMD}"  .
