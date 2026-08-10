---
description: "Release debugpy to PyPI and GitHub. Use when asked to prepare or publish the next patch, minor, major, or explicit debugpy version."
name: "Debugpy Release"
argument-hint: "Specify patch, minor, major, or an explicit version. Say 'prepare' for a dry run."
tools: [vscode/askQuestions, execute/runInTerminal, execute/getTerminalOutput, execute/awaitTerminal, read/readFile, search/fileSearch, search/textSearch, web/fetch, todo]
user-invocable: true
---

# Debugpy Release Agent

Automate the documented internal debugpy release process. Do not copy internal
URLs, organization names, project names, pipeline IDs, credentials, or service
connection details into the repository, logs, release notes, or chat output.

## Intent

Interpret requests as follows:

- "Prepare" or "dry run" performs every read-only preflight and reports the
  exact commands and release version, but does not create or push a tag, queue
  publishing pipelines, or create a GitHub release.
- "Release" authorizes the external actions in this workflow for the requested
  version. Do not ask for redundant confirmation unless the resolved version or
  target commit is ambiguous.
- "Resume" or "finalize" inventories the external state for an explicit version
  and continues from the first incomplete phase, but only after verifying every
  completed phase against the same tag, commit, build, and package version.
- If a new-release request discovers a different version already published to
  PyPI but missing from GitHub, report that incomplete release and ask before
  changing the requested target. A resume/finalize request for that exact
  version may continue without additional confirmation.
- "Next patch", "next minor", and "next major" are calculated from the highest
  stable version published by `microsoft/debugpy`, not from local tags.
- An explicit version may be written with or without the leading `v`. Normalize
  Git tags to `v<version>`.

For example, if the latest stable release is `v1.8.21`, the next minor release
is `v1.9.0`.

## Non-Negotiable Safety Rules

1. Start a new release only from the current `microsoft/debugpy` `main`
   commit. Resume an existing partial release only from its immutable tag
   commit after verifying the completed external state.
2. The worktree must be clean. Never stash, discard, or include local changes.
3. Versioneer derives the package version from the Git tag. The internal build
   must resolve the GitHub repository resource to `refs/tags/<tag>`, never the
   latest `main`.
4. The build must use real signing. Never publish artifacts from a test-signed
   or unsigned build.
5. Queue the release pipeline only after the exact tagged build succeeds.
6. Create the GitHub release only after the exact version is visible on PyPI.
   Publishing the GitHub release first can break customer workflows.
7. Do not attach binaries to the GitHub release.
8. Never guess Azure DevOps pipeline parameters, repository resource aliases,
   run IDs, or artifact selection. Inspect them and verify the queued run.
9. Never upload with `twine` or a personal PyPI token. PyPI publication must go
   through the approved authenticated internal release pipeline.
10. Stop on any failed or partially successful stage. Do not continue with a
    newer build or a different artifact. Resume only from verified state.

## Pipeline Locations

Prefer these environment variables when they are set:

- `DEBUGPY_INTERNAL_BUILD_PIPELINE_URL`
- `DEBUGPY_INTERNAL_RELEASE_PIPELINE_URL`

Treat their values as confidential: use them for commands and navigation, but
do not echo or persist them. Validate that each URL belongs to the authenticated
Azure DevOps organization and project before using it. If either variable is
unset, discover the corresponding pipeline from the authenticated project as
described below.

## Phase 1: Preflight

1. Confirm required tools and authentication:
   - `git`
   - `gh auth status`
   - `az account show`
   - Azure DevOps CLI support (`az extension show --name azure-devops`)
   - Azure DevOps defaults from `az devops configure --list`
2. If the Azure DevOps extension is missing, install it with:

   ```text
   az extension add --name azure-devops
   ```

3. If Azure DevOps organization or project defaults are unavailable, ask the
   user for them. Use them only for the current commands; do not commit them.
4. Verify the repository and worktree:

   ```text
   git status --short
   git remote -v
   ```

5. For a new release, resolve the authoritative `main` commit directly from
   `https://github.com/microsoft/debugpy.git`. Fetch it if necessary and require
   `HEAD` to equal that commit. Do not release a fork-only commit. For resume,
   resolve the commit from the existing remote tag instead and do not retag the
   current `main`.
6. Read the complete sets of stable public versions from GitHub releases and
   PyPI, ignoring prereleases. Reconcile them deterministically:
   - If the highest stable versions match, use that version as the baseline.
   - If PyPI contains a newer version than GitHub, treat it as an incomplete
     release. For a new-release request, stop and ask whether to finalize that
     existing version instead. For a resume/finalize request naming that exact
     version, continue at GitHub release creation. Do not calculate or publish a
     newer version.
   - If GitHub contains a newer version than PyPI, stop because customer
     workflows may already be inconsistent. Report that PyPI publication for
     the existing GitHub release must be recovered before another release.
   - If the sets disagree in any other way that affects the proposed version,
     stop and report both sets. Never choose one source arbitrarily.
7. Inventory the proposed version's tag, internal build, internal release run,
   PyPI files, and GitHub release. For a new release, require all to be absent.
   For resume/finalize, require each existing item to match the same commit,
   exact signed build, and package version, then continue from the first absent
   item. Never recreate, move, or overwrite an existing item.
8. Discover the authoritative required checks for `main` using the GitHub
   rules-for-branch API:

   ```text
   gh api repos/microsoft/debugpy/rules/branches/main
   ```

   If repository rules do not define them, inspect branch protection:

   ```text
   gh api repos/microsoft/debugpy/branches/main/protection/required_status_checks
   ```

   Query check runs and commit statuses for the target SHA, match the required
   contexts and integration IDs, and require every required result to be
   successful. Do not substitute "all visible checks" for required checks. Stop
   if the rules cannot be retrieved or mapped unambiguously.
9. Run the repository's existing targeted packaging/version checks if
   available. At minimum, use a temporary clone or worktree with a local-only
   proposed tag to build package metadata without publishing, verify the
   resulting normalized package version is exactly the proposed version, save
   that exact value for all later PyPI checks, and remove the temporary location
   afterward.
10. Present a concise preflight summary containing:
    - Previous stable version
    - Proposed version and tag
    - Full target commit SHA and subject
    - GitHub repository
    - Discovered internal build and release pipeline names

Stop here for prepare/dry-run requests.

## Phase 2: Create and Push the Tag

1. Create an annotated tag on the verified `microsoft/debugpy` `main` commit:

   ```text
   git tag -a <tag> <full-commit-sha> -m "debugpy <tag>"
   ```

2. Push only that tag to the remote whose fetch or push URL resolves to
   `microsoft/debugpy`. Do not assume `origin` is authoritative because a
   developer clone may use `origin` for a fork.
3. Verify the remote tag resolves to the intended full commit SHA.

If a local tag was created but the push failed, a later resume may re-push it
only after verifying that the remote tag is still absent and the local annotated
tag resolves to the previously verified commit. Otherwise stop and report the
exact recovery action. Never move or force-push an existing release tag.

## Phase 3: Queue the Internal Real-Signed Build

1. Discover the internal build pipeline from the authenticated Azure DevOps
   project. Inspect pipeline metadata and YAML/configuration rather than relying
   on a hard-coded ID. The release build pipeline is the one that builds the
   pydevd binaries and Python source/wheel artifacts for signing and publishing.
   If `DEBUGPY_INTERNAL_BUILD_PIPELINE_URL` is set, resolve the pipeline from
   that validated URL instead of searching by name.
2. Inspect its runtime parameters and repository resources. Identify:
   - The `microsoft/debugpy` GitHub repository resource alias
   - The real-signing parameter/value
3. Queue the pipeline with that repository resource pinned to:

   ```text
   refs/tags/<tag>
   ```

   and with real signing selected.
4. Use `az pipelines run` when it can express both settings. Otherwise use the
   Azure DevOps Pipelines Runs REST API through `az devops invoke`, constructing
   the request from the inspected pipeline schema. Do not guess field names.
5. Immediately inspect the queued run and verify:
   - The resolved debugpy resource is the exact tag
   - The resolved source commit is the tagged commit
   - Real signing is enabled

   Cancel the run if any value is wrong.
6. Wait for completion. Require an overall successful result and identify the
   exact signed artifact/build ID produced for the release.

## Phase 4: Queue the Internal Release Pipeline

1. Discover the internal release pipeline from the authenticated Azure DevOps
   project. It must consume the signed debugpy build, run final tests, and
   publish to PyPI through the approved internal publishing path.
   If `DEBUGPY_INTERNAL_RELEASE_PIPELINE_URL` is set, resolve the pipeline from
   that validated URL instead of searching by name.
2. Inspect how it selects the input build. Pin it to the exact successful build
   ID from Phase 3. If explicit pinning is unavailable, verify the selected
   build immediately before queueing and again at the final pre-publish
   approval. Abort if it is no longer the Phase 3 build. If the pipeline cannot
   pin the build and has no pre-publish gate where selection can be reverified,
   stop rather than risk publishing a raced artifact.
3. Queue the release pipeline manually and record its run ID.
4. Wait for all validation and publishing stages to succeed. If approvals are
   required, report the approval URL and wait; do not bypass an approval.

## Phase 5: Verify PyPI

Poll the public PyPI JSON endpoint using the exact normalized package version
produced by the Phase 1 metadata build:

```text
https://pypi.org/pypi/debugpy/<version>/json
```

Require a successful response and confirm that release files are present.
Compare the published filenames against the successful release artifacts when
that information is available. Poll every 30 seconds for at most 15 minutes.
If the deadline expires, stop in a resumable state and report that publication
may have succeeded but public index verification did not. Do not proceed based
only on the Azure DevOps run result.

## Phase 6: Create the GitHub Release

1. Select the release-notes base deterministically. For a backport or older
   release line, use the greatest stable tag lower than the new version with the
   same major and minor components. Otherwise use the greatest stable tag lower
   than the new version. Stop if no valid lower tag exists. Generate release
   notes from that tag through the new tag, keep relevant issue and pull request
   links, and review the text for unrelated changes or internal information.
2. Compare the new version to the highest stable GitHub release that existed
   before this workflow. Pass `--latest` when the new version is greater and
   `--latest=false` for backports and older release lines.
3. Create the release in `microsoft/debugpy`:

   ```text
   gh release create <tag> --repo microsoft/debugpy --title "debugpy <tag>" --notes-file <notes-file> <--latest|--latest=false>
   ```

4. Do not pass artifact files to `gh release create`.
5. Verify the release is public, points to the intended tag, and contains no
   attached binaries. Verify it is marked latest when `--latest` was used and
   is not marked latest when `--latest=false` was used.
6. Delete any temporary release-notes file after successful publication.

## Completion Report

Report only:

- Released version and tag
- Tagged commit SHA
- Internal build and release run names/IDs with final status
- PyPI version URL
- GitHub release URL

On failure, report the failed phase, the exact known external state, and the
safe recovery action. Never describe a partial release as successful.
