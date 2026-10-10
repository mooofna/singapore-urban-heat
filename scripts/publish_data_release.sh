#!/usr/bin/env bash
# Publish a packaged data snapshot as the rolling pre-release "data-latest" and keep the
# previous snapshot as "data-previous". Requires GH_TOKEN with contents:write.
set -euo pipefail

DIR="$1"
TARGET="${GITHUB_SHA:-$(git rev-parse HEAD)}"

if gh release view data-latest >/dev/null 2>&1; then
  PREV="$(mktemp -d)"
  gh release download data-latest --dir "$PREV" --clobber
  gh release delete data-previous --yes --cleanup-tag >/dev/null 2>&1 || true
  gh release create data-previous "$PREV"/* \
    --prerelease --latest=false --target "$TARGET" \
    --title "Data snapshot (previous)" \
    --notes "The data snapshot before the most recent monthly update. See data-latest for the current one."
  gh release delete data-latest --yes --cleanup-tag
fi

gh release create data-latest "$DIR"/* \
  --prerelease --latest=false --target "$TARGET" \
  --title "Data snapshot (latest)" \
  --notes-file "$DIR/NOTES.md"
