# GitHub releases and container publishing

The workflow `.github/workflows/docker-publish.yml` targets GHCR at `ghcr.io/<lowercase-owner>/<lowercase-repository>`. It uses `GITHUB_TOKEN`; a separate registry password is not needed. The repository must allow Actions and package publishing. Set package visibility in GitHub if images should be publicly pullable.

## Publish 1.0.0

1. Commit the project, including `.github`, to your GitHub repository's `main` branch.
2. Open GitHub → Releases → Draft a new release. Create tag **v1.0.0** from the intended commit.
3. Use [RELEASE-NOTES.md](../RELEASE-NOTES.md) as the release description and publish the release.
4. Wait for “Test and publish Docker image” to succeed. Check the resulting GHCR package and multi-platform manifests.

Uploading files or pushing a version tag alone does not trigger a release publication; the workflow listens to the GitHub `release: published` event. The source tree here is prepared for this operation; no remote release is created by preparing this archive.

## What runs

- Python/Node source versions must agree. For a release, its tag must match `v` plus the embedded version.
- Frontend tests/build and backend tests run with QuickJS-NG.
- Alpine is built on native amd64 and arm64 runners.
- Each image is checked offline against a temporary database: JS/EJS, API, frontend, local yt-dlp/FFmpeg download and media streaming.
- Only successful builds are pushed by digest. Version/rolling tags are assembled after both image jobs succeed. Package visibility is configured separately in GitHub.

Stable releases publish `1.0.0`, `1.0`, `1`, `latest` and `1.0.0-alpine` for Alpine; Debian is only available as a local build. Pre-releases get only their complete version tags, never stable rolling tags. Main-branch pushes update `main`, `main-alpine`; pull requests and manual runs test without publishing.

For subsequent releases, update `app/__init__.py`, `frontend/package.json` and both version entries in `frontend/package-lock.json`, update release notes/changelog, and publish the matching `vX.Y.Z` release. `python scripts/release.py` checks version consistency locally.
