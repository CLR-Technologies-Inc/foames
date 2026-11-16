# Changelog fragments

Pull requests do not edit `CHANGELOG.md`. Each one adds a small file here instead, so two pull requests never touch the same changelog lines and never conflict over them. A release collects the fragments into a new `CHANGELOG.md` section and deletes them.

## Adding one

Name the file `<id>.<category>.md`:

- `<id>` is the pull request number (`81`), or a short slug (`pfmea-export`) when you do not have the number yet. A numeric id gets `(#81)` appended to its first line.
- `<category>` is one of `added`, `changed`, `fixed`, `security`, `deprecated`, `removed` or `docs`.

Write one line per change, in plain sentences for someone who runs FoaMES. Lines may start with `- `; others become bullets.

```text
changelog.d/81.added.md
Work instructions can be printed as a controlled PDF from the desk.
```

A pull request with no user-facing change (CI, refactors, tests) needs no fragment.

## Checking and previewing

```bash
python .github/scripts/release.py check     # names and categories (CI runs this)
python .github/scripts/release.py preview   # the next CHANGELOG section
```

How versions, pre-releases and tags work: [docs/versioning.md](../docs/versioning.md).
