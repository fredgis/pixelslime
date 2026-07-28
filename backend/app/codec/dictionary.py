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
from functools import cache
from pathlib import Path

from .errors import DictionaryError

# Dictionary version 1, byte-for-byte. This hash is the pin; bump both together.
_DICT_VERSION = 1
_DICT_FILENAME = "psdict_v1.bin"
_DICT_SHA256 = "a9cbf34dd2f51306cf165329bcf9a50efd1733fa6d787b5cdc866b37543889f0"

# codec -> app -> backend -> repo root -> assets/
_ASSETS_DIR = Path(__file__).resolve().parents[3] / "assets"


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
    path = _ASSETS_DIR / _DICT_FILENAME
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
