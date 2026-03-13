#!/usr/bin/env python3

import json
import re
from urllib.parse import urlparse

INPUT_FILE = "backend/sources.json"
OUTPUT_FILE = "backend/sources_deduplicated.json"


def normalize_name(name):
    """Lowercase and remove punctuation for comparison."""
    name = name.lower()
    name = re.sub(r"[^\w\s]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def normalize_url(url):
    """Normalize URL for comparison."""
    url = url.strip()

    # remove trailing slash
    if url.endswith("/"):
        url = url[:-1]

    parsed = urlparse(url)

    # normalize scheme + host + path
    normalized = f"{parsed.netloc.lower()}{parsed.path}"

    return normalized


def dedupe_sources(sources):
    seen_urls = set()
    seen_names = set()

    clean = []
    duplicates = []

    for src in sources:
        name = src.get("name", "").strip()
        url = src.get("url", "").strip()

        norm_name = normalize_name(name)
        norm_url = normalize_url(url)

        if norm_url in seen_urls or norm_name in seen_names:
            duplicates.append(src)
            continue

        seen_urls.add(norm_url)
        seen_names.add(norm_name)

        clean.append(src)

    return clean, duplicates


def main():
    with open(INPUT_FILE, "r") as f:
        sources = json.load(f)

    clean, duplicates = dedupe_sources(sources)

    with open(OUTPUT_FILE, "w") as f:
        json.dump(clean, f, indent=2)

    print(f"Original sources: {len(sources)}")
    print(f"Unique sources:   {len(clean)}")
    print(f"Duplicates:       {len(duplicates)}")
    print(f"Output written to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
