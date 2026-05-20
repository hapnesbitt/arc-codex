"""
Generic loader for (name, name2, url) catalogs defined as Python list literals
in standalone files (e.g. /home/ross/dual.py, /home/ross/perennials.py).

Designed for reuse: any future surface that wants a curated table-of-contents
view (syndromes, glossaries, etc.) can declare its data in a Python file and
serve it via this loader without inventing new schemas.

Loads with importlib so the source files do not need to sit on sys.path.
Side-effects from module top-level (e.g. os.makedirs) are isolated by
executing the module while CWD is a throwaway temp directory.
"""

import importlib.util
import os
import tempfile
from typing import List, Dict


def load_catalog(filepath: str, list_name: str) -> List[Dict[str, str]]:
    """Load a (common, latin, url) catalog from a Python file.

    Args:
        filepath: Absolute path to the Python file containing the catalog.
        list_name: Variable name of the list literal inside that file.

    Returns:
        List of {'common', 'latin', 'url'} dicts, preserving source order.

    Raises:
        FileNotFoundError, ImportError, AttributeError.
    """
    if not os.path.isfile(filepath):
        raise FileNotFoundError(filepath)

    module_name = f"_catalog_{list_name}_{abs(hash(filepath))}"
    spec = importlib.util.spec_from_file_location(module_name, filepath)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not build import spec for {filepath}")
    module = importlib.util.module_from_spec(spec)

    saved_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as sandbox:
        try:
            os.chdir(sandbox)
            spec.loader.exec_module(module)
        finally:
            os.chdir(saved_cwd)

    raw = getattr(module, list_name, None)
    if raw is None:
        raise AttributeError(f"{filepath} has no attribute '{list_name}'")

    out: List[Dict[str, str]] = []
    for row in raw:
        if not row or len(row) < 3:
            continue
        common, latin, url = row[0], row[1], row[2]
        if not (common and latin and url):
            continue
        out.append({
            'common': str(common),
            'latin': str(latin),
            'url': str(url),
        })
    return out
