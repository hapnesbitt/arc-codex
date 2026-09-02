# Library original-publication metadata

Arc keeps two date concepts separate:

- `year_published` is the existing legacy field populated from Project
  Gutenberg RDF `dcterms:issued`. It is the Gutenberg electronic-edition
  release year, not the source work's original publication year.
- `original_publication_year` is nullable and is set only when explicit,
  auditable evidence is available.

The accompanying fields are `original_publication_source`,
`original_publication_confidence`, `original_publication_evidence`, and
`original_publication_checked_at`. Unknown is represented by SQL `NULL`, never
zero. Evidence is a short structured description, not a copyrighted excerpt.

Automatic extraction accepts only explicit `first published YEAR` or
`originally published YEAR` statements near the start of a Gutenberg
description or stored ebook text. Bare copyright years, edition years,
Gutenberg release dates, Gutenberg ID order, author lifespans, and ordinary
prose years are ignored.

Source precedence is:

1. `manual`
2. `bibliographic`
3. `gutenberg_description`
4. `gutenberg_text`

A lower-precedence refresh cannot replace a higher-precedence value. Equal
precedence replaces only lower confidence. A deliberate manual correction can
replace any prior value.

## Incremental backfill

The backfill reads only text already stored in `library.db`; it does not access
Gutenberg or change shelves, scores, or translations.

```bash
cd /home/www/arc_stack/backend
venv/bin/python publication_year_backfill.py --limit 100
venv/bin/python publication_year_backfill.py --limit 100 --after-id 20000
venv/bin/python publication_year_backfill.py --limit 100 --min-id 20000 --max-id 30000
venv/bin/python publication_year_backfill.py --limit 100 --shelf american_history
```

Checked records with no reliable evidence remain NULL and are skipped by later
runs. Use `--retry-checked` deliberately after improving extraction rules.
There is no cron entry and a mass backfill is not part of deployment.

## Manual verification

Use the database helper inside a transaction rather than writing columns
independently:

```python
import library_db

with library_db.db() as conn:
    library_db.set_manual_original_publication_year(
        conn,
        12345,
        1930,
        evidence="verified against publisher first-edition catalog record",
    )
```

Manual values use source `manual` and confidence `1.0`. The helper validates
the year and normalizes evidence to at most 240 characters.

## Future queries

```sql
SELECT gutenberg_id, title, author, original_publication_year
FROM works
WHERE original_publication_year IS NOT NULL
ORDER BY original_publication_year DESC
LIMIT 100;
```

```sql
SELECT original_publication_year, COUNT(*)
FROM works
WHERE original_publication_year IS NOT NULL
GROUP BY original_publication_year
ORDER BY original_publication_year DESC;
```
