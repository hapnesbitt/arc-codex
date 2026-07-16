# Catalog source files (repo record)

Canonical copies of the host catalog files that Flask reads by absolute
path (see PLANTS_ANNUALS_FILE / PLANTS_PERENNIALS_FILE in main.py):

- `dual.py`        → /home/ross/dual.py        (annuals — the plant→hash manifest, incl. the 2026-07-16 Pentas fix ff062b03…)
- `perennials.py`  → /home/ross/perennials.py  (perennials)

The live files on the host are still the ones Flask serves. If you edit
one, update the copy here in the same change. /home/ross/syndromes.py is
the remaining untracked sibling (see SYNDROMES_FILE).
