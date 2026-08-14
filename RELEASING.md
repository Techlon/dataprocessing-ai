# Releasing

Publishing runs from GitHub Actions using PyPI **Trusted Publishing**, so there
is no API token anywhere — not in a secret, not in `~/.pypirc`, nothing to leak
or rotate. PyPI is configured to trust one workflow in one repository, and
GitHub proves the workflow's identity with a short-lived OpenID Connect token
issued per run.

## One-time setup

This has to be done by the account owner; it cannot be scripted from here.

**1. Add the trusted publisher on PyPI.**

Go to <https://pypi.org/manage/account/publishing/> and add a pending publisher:

| Field | Value |
|---|---|
| PyPI project name | `dataprocessing-ai` |
| Owner | `Techlon` |
| Repository name | `dataprocessing-ai` |
| Workflow name | `release.yml` |
| Environment name | `pypi` |

Repeat at <https://test.pypi.org/manage/account/publishing/> with the
environment name `testpypi` if you want the rehearsal path.

The `dataprocessing-ai` project already exists on PyPI, so add the publisher
from the project's own *Publishing* settings rather than as a pending one.

**2. Create the GitHub environments.**

In the repository settings, under *Environments*, create `pypi` and `testpypi`.
Adding a required reviewer to `pypi` means a release waits for an approval
click, which is worth having for an irreversible upload.

## Releasing

```bash
# 1. Bump the version. It lives in exactly one place.
#    dataprocessing.__version__ reads it back from the installed metadata.
$EDITOR pyproject.toml
grep '^version' pyproject.toml

# 2. Update CHANGELOG.md.

# 3. Commit, tag, push. The tag triggers the release workflow.
git add -A && git commit -m "Release vX.Y.Z"
git tag vX.Y.Z
git push && git push --tags
```

The workflow builds, runs `twine check`, and **refuses to publish if the tag and
the version in `pyproject.toml` disagree** — a PyPI version can never be reused,
so that mismatch is worth failing on rather than discovering afterwards.

To rehearse without tagging, run the workflow manually from the Actions tab with
*Publish to TestPyPI* left ticked.

## Verifying a release

CI already installs the built wheel and imports it from outside the repository
on every run. To check the live release as a stranger would:

```bash
python3 -m venv /tmp/verify && source /tmp/verify/bin/activate
pip install "dataprocessing-ai[all]"
cd /tmp    # outside the source tree, or you import local files instead
python -c "import dataprocessing; print(dataprocessing.__version__)"
python -c "from dataprocessing import mcp_server; print('mcp ok')"
deactivate && rm -rf /tmp/verify
```

## If you would rather use a token

Trusted publishing is the better default, but a token still works:

```bash
python -m build
twine check dist/*
twine upload --repository testpypi dist/*    # rehearse first
twine upload dist/*
```

PyPI and TestPyPI are separate accounts with separate tokens; one will 403 on
the other. Tokens go in `~/.pypirc`, which must never be committed.
