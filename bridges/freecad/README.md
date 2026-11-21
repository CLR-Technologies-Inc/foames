# foames-freecad

Read-only bridge that lets FoaMES inspect native FreeCAD documents without FreeCAD in the Frappe runtime. Standard library only; FreeCAD itself is reached through a separate runtime the operator installs — this package never imports it.

The guide is [docs/vendors/freecad/](../../docs/vendors/freecad/README.md); agent rules are in [AGENTS.md](AGENTS.md).

```bash
pip install .
python -m foames_freecad health       --config examples/freecad.json
python -m foames_freecad capabilities --config examples/freecad.json
python -m foames_freecad inspect      --config examples/freecad.json part.FCStd
python -m unittest discover -s tests -v
```

Licensed under the Apache License, Version 2.0, like FoaMES. It contains no FreeCAD code and uses only FreeCAD's published document format through its own Python runtime.
