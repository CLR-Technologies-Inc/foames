# foames-bluesky

Bridge from [Bluesky](https://github.com/bluesky/bluesky) runs, live, from a [Tiled](https://github.com/bluesky/tiled) catalog or from JSON Lines files, to FoaMES `Measurement` events through the signed machine-event webhook. Standard library only; Bluesky and the Tiled client are optional.

The guide, with what each document becomes and how to chart the results, is [docs/vendors/bluesky/](../../docs/vendors/bluesky/README.md).

```bash
pip install .            # or .[tiled] to read from Tiled
export FOAMES_WEBHOOK_SECRET=...
python -m foames_bluesky jsonl run.jsonl --machine uvvis-1 --summary mean --dry-run
python -m unittest discover -s tests -v
```

Licensed under the Apache License, Version 2.0, like FoaMES. Bluesky and Tiled are BSD-3-Clause projects of Brookhaven Science Associates; this package contains none of their code and only uses their published document model and client API.
