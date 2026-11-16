# Wiki source

This folder is the source of the [FoaMES GitHub wiki](https://github.com/CLR-Technologies-Inc/foames/wiki). The `Wiki sync` workflow (`.github/workflows/wiki.yml`) copies every page here except this README to the wiki whenever it changes on `main`, so edit the pages here, through a pull request, rather than on the wiki itself. Edits made directly on the wiki are overwritten by the next sync.

The pages follow [Diátaxis](https://diataxis.fr/): `Tutorial-*` pages teach, `How-to-*` pages solve a task, `Reference-*` pages describe, and `Explanation-*` pages discuss why. `_Sidebar.md` and `_Footer.md` appear on every wiki page. Links between pages use the page name without `.md`, as the wiki expects.

`Reference-DocTypes.md` and `Reference-Settings.md` were generated from the DocType JSON files; regenerate or update them when a DocType changes. Describe only what is on `main`; features still in review go on `Upcoming-features.md`.
