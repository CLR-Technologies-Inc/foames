# foames-openfoam

Isolated OpenFOAM CFD runner and provider contract for FoaMES. Standard library only; OpenFOAM's GPL binaries live in the worker image and are invoked as a separate process — never linked, never bundled.

The guide is [docs/vendors/openfoam/](../../docs/vendors/openfoam/README.md); the Frappe side is `foames/foames_simulation/` in the app.

```bash
pip install .
python -m foames_openfoam cases
python -m foames_openfoam run --case pitzdaily --params '{"end_time": 300}'
python -m foames_openfoam serve --config examples/openfoam.json --port 8765
python -m unittest discover -s tests -v
```

Licensed under the Apache License, Version 2.0, like FoaMES.
