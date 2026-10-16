# nemotron-data (private)

NVIDIA Nemotron-Personas-Korea `nemotron.parquet` (1,000,000 rows, 72 row groups) split **byte-for-byte** into Release assets so the `nemotron-panel-synthesis` skill can run without a local copy.

- Nothing is re-encoded: each asset is an exact byte range of the original file.
- `manifest.json` lists every part with its offset, length and sha256.
- `nemotron_remote.py` rebuilds a sparse local file of the original size and fills only the ranges a run needs.
