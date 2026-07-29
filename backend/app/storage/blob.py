"""Async Blob Storage access with deterministic, human-readable paths.

Images live in private containers and are proxied by the API, so the store's job is
just: fetch bytes + ETag, upload the pair the job produces, and load/save the
``index.json`` snapshot the read-path uses to warm-start. Paths are deterministic —
``cards/PS-0042.png`` and ``thumbs/PS-0042.webp`` — so a serial fully determines
its blob with no lookup. The zero-padding matches the ``PS-0001`` id printed on the
card art (four digits; widens naturally past 9999).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

INDEX_BLOB_NAME = "index.json"


def card_blob_name(serial: int) -> str:
    """Blob name of a card PNG within the ``cards`` container."""
    return f"PS-{serial:04d}.png"


def thumb_blob_name(serial: int) -> str:
    """Blob name of a card thumbnail within the ``thumbs`` container."""
    return f"PS-{serial:04d}.webp"


class StorageError(RuntimeError):
    """Base class for storage failures."""


class BlobNotFound(StorageError):  # noqa: N818
    """A requested blob does not exist."""


@dataclass(frozen=True)
class BlobDownload:
    """Bytes plus the metadata the proxy routes need for caching."""

    data: bytes
    etag: str
    content_type: str


@runtime_checkable
class BlobStore(Protocol):
    """The storage surface the API depends on."""

    async def get_card_png(self, serial: int) -> BlobDownload: ...

    async def get_thumb(self, serial: int) -> BlobDownload: ...

    async def put_card(self, serial: int, png: bytes, webp: bytes) -> None: ...

    async def load_index(self) -> bytes | None: ...

    async def save_index(self, data: bytes) -> None: ...

    async def aclose(self) -> None: ...


def _weak_etag(data: bytes) -> str:
    """A stable content-addressed ETag for the fake store."""
    return hashlib.sha256(data).hexdigest()[:32]


class InMemoryBlobStore:
    """A dict-backed blob store for tests and ``LOCAL_DEV`` runs."""

    def __init__(self) -> None:
        self._cards: dict[int, bytes] = {}
        self._thumbs: dict[int, bytes] = {}
        self._index: bytes | None = None

    def seed_card(self, serial: int, png: bytes, webp: bytes) -> None:
        """Populate a card/thumb pair without going through the async API."""
        self._cards[serial] = png
        self._thumbs[serial] = webp

    async def get_card_png(self, serial: int) -> BlobDownload:
        data = self._cards.get(serial)
        if data is None:
            raise BlobNotFound(card_blob_name(serial))
        return BlobDownload(data=data, etag=_weak_etag(data), content_type="image/png")

    async def get_thumb(self, serial: int) -> BlobDownload:
        data = self._thumbs.get(serial)
        if data is None:
            raise BlobNotFound(thumb_blob_name(serial))
        return BlobDownload(data=data, etag=_weak_etag(data), content_type="image/webp")

    async def put_card(self, serial: int, png: bytes, webp: bytes) -> None:
        self._cards[serial] = png
        self._thumbs[serial] = webp

    async def load_index(self) -> bytes | None:
        return self._index

    async def save_index(self, data: bytes) -> None:
        self._index = data

    async def aclose(self) -> None:
        return None


class AzureBlobStore:
    """Blob access backed by Azure using a managed identity.

    Three separate containers (``cards``/``thumbs``/``assets``) mirror
    ``infra/modules/storage.bicep``. The service client is created eagerly but does no
    network I/O until a blob is touched, so constructing it during app startup is cheap.
    """

    def __init__(
        self,
        account_url: str,
        *,
        cards_container: str,
        thumbs_container: str,
        assets_container: str,
        index_blob_name: str = INDEX_BLOB_NAME,
    ) -> None:
        from azure.identity.aio import DefaultAzureCredential
        from azure.storage.blob.aio import BlobServiceClient

        self._credential = DefaultAzureCredential()
        self._service = BlobServiceClient(account_url, credential=self._credential)
        self._cards_container = cards_container
        self._thumbs_container = thumbs_container
        self._assets_container = assets_container
        self._index_blob_name = index_blob_name

    async def _download(self, container: str, name: str, content_type: str) -> BlobDownload:
        from azure.core.exceptions import ResourceNotFoundError

        blob = self._service.get_blob_client(container, name)
        try:
            stream = await blob.download_blob()
            data = await stream.readall()
        except ResourceNotFoundError as exc:
            raise BlobNotFound(f"{container}/{name}") from exc
        etag = (stream.properties.etag or _weak_etag(data)).strip('"')
        return BlobDownload(data=data, etag=etag, content_type=content_type)

    async def _upload(self, container: str, name: str, data: bytes, content_type: str) -> None:
        from azure.storage.blob import ContentSettings

        blob = self._service.get_blob_client(container, name)
        await blob.upload_blob(
            data,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type),
        )

    async def get_card_png(self, serial: int) -> BlobDownload:
        return await self._download(self._cards_container, card_blob_name(serial), "image/png")

    async def get_thumb(self, serial: int) -> BlobDownload:
        return await self._download(self._thumbs_container, thumb_blob_name(serial), "image/webp")

    async def put_card(self, serial: int, png: bytes, webp: bytes) -> None:
        await self._upload(self._cards_container, card_blob_name(serial), png, "image/png")
        await self._upload(self._thumbs_container, thumb_blob_name(serial), webp, "image/webp")

    async def load_index(self) -> bytes | None:
        from azure.core.exceptions import ResourceNotFoundError

        blob = self._service.get_blob_client(self._assets_container, self._index_blob_name)
        try:
            stream = await blob.download_blob()
            return await stream.readall()
        except ResourceNotFoundError:
            return None

    async def save_index(self, data: bytes) -> None:
        await self._upload(self._assets_container, self._index_blob_name, data, "application/json")

    async def aclose(self) -> None:
        await self._service.close()
        await self._credential.close()
