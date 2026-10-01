#!/usr/bin/env python3
"""round2_provenance_restore.py — the authors retract the v0.50 correction (prereg v0.51).

The authors affirm that the 'prefill' line in the round-2 decisions export was accurate after all:
the 81 rows were AI-prefilled from public HQ/ownership information and then reviewed and finalised
by the authors, exactly as prereg v0.49 recorded; the v0.50 statement arose from a mix-up over
which export file was which.

Restoration is done by REGENERATION, not text edit: the pre-extension backups
(*.pre-round2.csv) are restored as the live tables and build_round2_extension.py is re-run on the
unchanged decisions, which reproduces the v0.49 files byte-for-byte. (The v0.50 correction script
had also normalised the files' CRLF line endings to LF as a side effect of its text edit, which is
why v0.50's hashes differ from v0.49's by more than the source strings; regeneration undoes that
too.) This script verifies the outcome."""
import hashlib
from pathlib import Path

W = Path("/home/claude/w")
EXPECT = {
    "brand_aliases.csv": "0b7bd5e8355c919300129b6ba96008d5cb2d95a691aaf759a1e82823ee2b00ea",   # v0.49
    "retailer_classification.csv": "94abc294de6fc82c6583d1e9be08bc7443e49008376cf2a718cd6febd19cf22a",  # v0.49
}
for name, want in EXPECT.items():
    h = hashlib.sha256((W / name).read_bytes()).hexdigest()
    assert h == want, f"{name}: {h} != v0.49 value {want}"
    src = (W / name).read_text(encoding="utf-8")
    assert "AI-prefilled from public HQ/ownership info; author-reviewed and finalised" in src
    print(f"{name}: sha256 {h[:8]}… == v0.49 value, v0.49 source strings present — VERIFIED")
