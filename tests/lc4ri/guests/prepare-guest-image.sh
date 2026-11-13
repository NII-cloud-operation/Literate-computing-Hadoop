#!/usr/bin/env bash
set -euo pipefail
source tests/lc4ri/guests/guest-image.env
mkdir -p "$1"
image="$1/$HDFS_E2E_GUEST_IMAGE"
if ! echo "$HDFS_E2E_GUEST_IMAGE_SHA256  $image" | sha256sum --check --status; then
  curl --fail --location --retry 3 "$HDFS_E2E_GUEST_IMAGE_URL" -o "$image"
fi
echo "$HDFS_E2E_GUEST_IMAGE_SHA256  $image" | sha256sum --check
