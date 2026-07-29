"""Loader for the pinned PSC-1 preset DEFLATE dictionary.

The dictionary is the whole trick that lets a card fit in one or two rows: on
strings this short, DEFLATE alone barely helps, but primed with the PixelSlime
vocabulary it saves 35-50%. Because the compressed body is meaningless unless the
*exact same* dictionary bytes are used to inflate it, the dictionary is pinned by
the header ``version`` byte (``0x01`` → ``psdict_v1.bin``) and additionally guarded
here by a SHA-256 check: if the asset is missing, truncated or silently swapped,
we refuse to run rather than emit bodies nobody can decode. See ``docs/CODEC.md``
§3.5 and ``scripts/build_dict.py``.
"""

from __future__ import annotations

import hashlib
import os
from functools import cache
from pathlib import Path

from .errors import DictionaryError

# Dictionary version 1, byte-for-byte. This hash is the pin; bump both together.
_DICT_VERSION = 1
_DICT_FILENAME = "psdict_v1.bin"
_DICT_SHA256 = "a9cbf34dd2f51306cf165329bcf9a50efd1733fa6d787b5cdc866b37543889f0"


def _assets_dir() -> Path:
    """Locate ``assets/`` without hard-coding a parent depth.

    This originally computed ``parents[3]``, which is correct in the source tree
    (``backend/app/codec/dictionary.py``) and wrong inside the container, where the
    package sits at ``/app/app/codec`` and the same arithmetic resolves to ``/``.
    The daily job therefore ran perfectly all the way to encoding a card and then
    died on a missing dictionary — a failure that could not appear until the image
    was actually deployed.

    So: an explicit override first, then a walk upwards looking for the directory,
    which is the approach ``app.ai.config.repo_root`` already used and the reason
    that module survived containerisation unchanged.
    """
    override = os.environ.get("PIXELSLIME_ASSETS_DIR", "").strip()
    if override:
        return Path(override)

    here = Path(__file__).resolve()
    for candidate in here.parents:
        assets = candidate / "assets"
        if (assets / _DICT_FILENAME).is_file():
            return assets
    # Nothing found: fall back to the source-tree layout so the error message names
    # the path a developer would expect rather than the filesystem root.
    return here.parents[3] / "assets"


@cache
def load_dictionary(version: int = _DICT_VERSION) -> bytes:
    """Return the preset dictionary bytes for ``version``, verifying its hash.

    Cached so the asset is read and hashed once per process. Raises
    :class:`DictionaryError` for an unknown version, a missing file or a hash
    mismatch — every one of which would otherwise corrupt every card silently.
    """
    if version != _DICT_VERSION:
        raise DictionaryError(
            f"unsupported dictionary version {version}; only {_DICT_VERSION} exists"
        )
    path = _assets_dir() / _DICT_FILENAME
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise DictionaryError(f"cannot read preset dictionary at {path}: {exc}") from exc
    actual = hashlib.sha256(data).hexdigest()
    if actual != _DICT_SHA256:
        raise DictionaryError(
            f"preset dictionary hash mismatch: expected {_DICT_SHA256}, got {actual}"
        )
    return data
