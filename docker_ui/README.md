# CorelDRAW Docker UI MVP

This folder is an original lightweight HTML UI that talks only to the local
FastAPI service at `http://127.0.0.1:8001`.

For initial testing, open `index.html` in a browser while `python main.py` is
running. To register it as a real CorelDRAW HTML Docker, copy these files into
an Addons folder and add an `AppUI.xslt` registration file matching the exact
CorelDRAW version. Corel changes the AppUI schema between releases, so the
registration file is intentionally not hard-coded here.

The UI does not call CorelDRAW COM directly. Python remains the single owner of
COM state, avoiding two controllers editing the same document concurrently.
