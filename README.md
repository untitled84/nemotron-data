# nemotron-data

Public mirror (CC BY 4.0, source: https://huggingface.co/datasets/nvidia/Nemotron-Personas-Korea) of NVIDIA Nemotron-Personas-Korea `nemotron.parquet` (1,000,000 rows, 72 row groups) split **byte-for-byte** into plain repository files (`parts/`) so the `nemotron-panel-synthesis` skill can run without a local copy.

- Nothing is re-encoded: each part is an exact byte range of the original file.
- `manifest.json` lists every part with its offset, length and sha256.
- `nemotron_remote.py` rebuilds a sparse local file of the original size and fills only the ranges a run needs.

## Layout
- `parts/` — 146 byte-range parts (`head`, `rgNN_s` = 35 structural columns, `rgNN_t` = 16 text columns, `footer`)
- `manifest.json` — offset / length / sha256 per part, plus the whole-file sha256
- `skill_scripts/` — `nemotron_remote.py` (`open_nemotron()`) and the remote-aware `signal_scan.py` for the nemotron-panel-synthesis skill

Verified 2026-10-16: reassembled sha256 equals the original (8128b83c…0332); 441 column reads, `load_adaptive` and `signal_scan --deep` output identical to the local original.
