"""Storage access owned by W7.

The blob container has public access disabled (``infra/modules/storage.bicep``),
so every image is proxied by the backend. This package hides that behind a small
:class:`~app.storage.blob.BlobStore` protocol with an Azure implementation and an
in-memory fake, so the API and tests never care which is behind them.
"""

from __future__ import annotations

from .blob import (
    AzureBlobStore,
    BlobDownload,
    BlobNotFound,
    BlobStore,
    InMemoryBlobStore,
    StorageError,
    card_blob_name,
    thumb_blob_name,
)

__all__ = [
    "AzureBlobStore",
    "BlobDownload",
    "BlobNotFound",
    "BlobStore",
    "InMemoryBlobStore",
    "StorageError",
    "card_blob_name",
    "thumb_blob_name",
]
