"""Core chunking data structures for Layer 3."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Chunk:
    """A retrieval-ready text chunk plus metadata payload."""

    chunk_id: str
    text: str
    raw_text: str
    source_type: str
    strategy: str
    metadata: dict[str, Any] = field(default_factory=dict)
    parent_id: str | None = None

    def to_payload(self) -> dict[str, Any]:
        payload = dict(self.metadata)
        payload.update(
            {
                "chunk_id": self.chunk_id,
                "source_type": self.source_type,
                "strategy": self.strategy,
                "parent_id": self.parent_id,
                "text": self.text,
            }
        )
        return payload


@dataclass(frozen=True)
class ChunkingConfig:
    """Defaults follow chunking_embedding_architecture.md."""

    child_token_target: int = 300
    child_token_overlap: int = 40
    cms_child_token_target: int = 512
    min_text_chars: int = 20
    include_embedding_text: bool = True


def estimate_tokens(text: str) -> int:
    """Cheap tokenizer-independent estimate for routing and tests."""

    return len(text.split())
