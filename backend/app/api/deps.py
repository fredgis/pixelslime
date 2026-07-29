"""FastAPI dependencies that hand routes what the lifespan built.

The heavy objects — the in-memory index, the blob store, the secret holder — are
created once in the app lifespan and stashed on ``app.state``. These thin accessors
pull them back out (typed) so the route signatures stay readable, and so tests can
swap the whole backend by constructing the app with fakes.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.core.config import Settings
from app.core.index import CardIndex
from app.core.secrets import SecretProvider
from app.storage.blob import BlobStore


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_index(request: Request) -> CardIndex:
    index: CardIndex = request.app.state.index
    return index


def get_blob(request: Request) -> BlobStore:
    blob: BlobStore = request.app.state.blob
    return blob


def get_secrets(request: Request) -> SecretProvider:
    secrets: SecretProvider = request.app.state.secrets
    return secrets


SettingsDep = Annotated[Settings, Depends(get_settings)]
IndexDep = Annotated[CardIndex, Depends(get_index)]
BlobDep = Annotated[BlobStore, Depends(get_blob)]
SecretsDep = Annotated[SecretProvider, Depends(get_secrets)]
