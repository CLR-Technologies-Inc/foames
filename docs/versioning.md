# Versioning and releases

FoaMES follows [Semantic Versioning](https://semver.org/). While it is 0.x, a minor version (0.2 to 0.3) may change DocTypes, APIs or MCP tools, so pin a tag if you build on it.

## Where the version lives

One place: `__version__` in [`foames/__init__.py`](../foames/__init__.py). Frappe shows it on the site's installed apps, the MCP server reports it to clients, the site CBOM records it and `pyproject.toml` reads it (`dynamic = ["version"]`). Nothing else holds a copy.

`__version__` is written in [PEP 440](https://peps.python.org/pep-0440/) form, and each Git tag is its SemVer twin:

| Stage | `__version__` | Git tag | GitHub release |
| --- | --- | --- | --- |
| In development on `main` | `0.3.0.dev0` | `v0.3.0-dev.0` (optional snapshot) | pre-release |
| Alpha / beta | `0.3.0a1`, `0.3.0b1` | `v0.3.0-alpha.1`, `v0.3.0-beta.1` | pre-release |
| Release candidate | `0.3.0rc1` | `v0.3.0-rc.1` | pre-release |
| Release | `0.3.0` | `v0.3.0` | latest |

`python .github/scripts/release.py tag` prints the tag for the current version.

## Which version a change goes to

- `main` always carries the next minor version as a `.dev` pre-release. Every enhancement merged to `main` ships in that version.
- 0.2.0 holds everything merged up to 2026-11-16. From 2026-11-16, new enhancements go to **0.3.0**, and `main` reads `0.3.0.dev0`.
- When 0.3.0 is released, `main` moves to `0.4.0.dev0` the same day, and so on: one minor version per release cycle.
- A fix to a released version that cannot wait for the next minor goes out as a patch (0.3.1) from a `release/0.3` branch, and is merged back to `main`.

## Changelog

`CHANGELOG.md` is written only at release time. Each pull request adds a fragment under [`changelog.d/`](../changelog.d/README.md) instead, so pull requests do not conflict over the changelog.

## Cutting a release

From an up-to-date `main`, on a release branch:

1. Optional release candidate: `python .github/scripts/release.py set 0.3.0rc1`, merge, and publish a pre-release tagged `v0.3.0-rc.1` from that commit.
2. `python .github/scripts/release.py set 0.3.0`
3. `python .github/scripts/release.py collect 0.3.0 --date YYYY-MM-DD` writes the section into `CHANGELOG.md` and deletes the fragments. Edit the section into release notes if it needs a summary.
4. Commit ("Release 0.3.0"), then `python .github/scripts/release.py set 0.4.0.dev0` and commit ("Start 0.4.0 development").
5. Merge the pull request with a merge commit (not a squash), so the release commit keeps its hash.
6. Publish the GitHub release with tag `v0.3.0` targeting the "Release 0.3.0" commit, using its `CHANGELOG.md` section as the notes.
