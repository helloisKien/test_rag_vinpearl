"""Hybrid chunking router for hotel, review, and CMS documents."""

from __future__ import annotations

import hashlib
from typing import Any

from .base import Chunk, ChunkingConfig, estimate_tokens
from .preprocess import clean_text, join_non_empty, make_context_prefix, split_markdown_sections, split_sentences


TEXT_METADATA_EXCLUDES = {
    "description",
    "description_full",
    "description_short",
    "embedding_text",
    "faq",
    "rooms",
    "activities",
    "reviews",
}


def stable_chunk_id(*parts: Any) -> str:
    raw = "|".join(clean_text(part) for part in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def with_context_prefix(text: str, title: str, section: str | None = None) -> str:
    prefix = make_context_prefix(title, section)
    body = clean_text(text)
    if not prefix:
        return body
    return f"{prefix}\n{body}"


def metadata_payload(record: dict[str, Any]) -> dict[str, Any]:
    """Keep exact/filterable fields in payload, not in embedded prose."""

    payload: dict[str, Any] = {}
    for key, value in record.items():
        if key in TEXT_METADATA_EXCLUDES or key.startswith("_"):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            payload[key] = value
        elif isinstance(value, list) and all(isinstance(item, (str, int, float, bool)) for item in value):
            payload[key] = value
    return payload


def whole_chunk(
    *,
    text: str,
    title: str,
    source_type: str,
    section: str,
    metadata: dict[str, Any],
    strategy: str = "whole",
    parent_id: str | None = None,
) -> Chunk | None:
    raw_text = clean_text(text)
    if not raw_text:
        return None
    chunk_id = stable_chunk_id(metadata.get("hotel_id") or metadata.get("document_id"), source_type, section, raw_text)
    return Chunk(
        chunk_id=chunk_id,
        text=with_context_prefix(raw_text, title, section),
        raw_text=raw_text,
        source_type=source_type,
        strategy=strategy,
        metadata={**metadata, "section": section},
        parent_id=parent_id,
    )


def recursive_sentence_chunks(
    *,
    text: str,
    title: str,
    source_type: str,
    section: str,
    metadata: dict[str, Any],
    target_tokens: int,
    overlap_tokens: int,
) -> list[Chunk]:
    sentences = split_sentences(text)
    if not sentences:
        return []

    parent_id = stable_chunk_id(metadata.get("hotel_id") or metadata.get("document_id"), source_type, section, "parent")
    chunks: list[Chunk] = []
    current: list[str] = []
    current_tokens = 0

    def emit() -> None:
        nonlocal current, current_tokens
        raw_text = clean_text(" ".join(current))
        if not raw_text:
            return
        index = len(chunks)
        chunks.append(
            Chunk(
                chunk_id=stable_chunk_id(parent_id, index, raw_text),
                text=with_context_prefix(raw_text, title, section),
                raw_text=raw_text,
                source_type=source_type,
                strategy="recursive_sentence",
                metadata={
                    **metadata,
                    "section": section,
                    "parent_id": parent_id,
                    "chunk_index": index,
                    "parent_text": clean_text(text),
                },
                parent_id=parent_id,
            )
        )
        if overlap_tokens <= 0:
            current = []
            current_tokens = 0
            return
        overlap: list[str] = []
        token_count = 0
        for sentence in reversed(current):
            count = estimate_tokens(sentence)
            if token_count + count > overlap_tokens:
                break
            overlap.insert(0, sentence)
            token_count += count
        current = overlap
        current_tokens = token_count

    for sentence in sentences:
        sentence_tokens = estimate_tokens(sentence)
        if current and current_tokens + sentence_tokens > target_tokens:
            emit()
        current.append(sentence)
        current_tokens += sentence_tokens
    emit()
    return chunks


def chunk_hotel(record: dict[str, Any], config: ChunkingConfig | None = None) -> list[Chunk]:
    config = config or ChunkingConfig()
    title = clean_text(record.get("name") or record.get("hotel_name") or f"hotel_{record.get('hotel_id', '')}")
    base_metadata = metadata_payload(record)
    base_metadata.setdefault("hotel_id", record.get("hotel_id"))
    base_metadata.setdefault("hotel_name", title)
    chunks: list[Chunk] = []

    short_text = join_non_empty([record.get("description_short"), record.get("overview")])
    chunk = whole_chunk(text=short_text, title=title, source_type="hotel", section="overview", metadata=base_metadata)
    if chunk:
        chunks.append(chunk)

    description = clean_text(record.get("description_full") or record.get("description"))
    chunks.extend(
        recursive_sentence_chunks(
            text=description,
            title=title,
            source_type="hotel",
            section="description",
            metadata=base_metadata,
            target_tokens=config.child_token_target,
            overlap_tokens=config.child_token_overlap,
        )
    )

    if config.include_embedding_text:
        chunk = whole_chunk(
            text=record.get("embedding_text", ""),
            title=title,
            source_type="hotel",
            section="semantic_profile",
            metadata=base_metadata,
            strategy="whole_semantic_profile",
        )
        if chunk:
            chunks.append(chunk)

    for index, room in enumerate(_list_of_dicts(record.get("rooms"))):
        room_text = _render_room(room)
        room_metadata = {**base_metadata, "room_index": index, "room_id": room.get("room_id") or room.get("id")}
        chunk = whole_chunk(
            text=room_text,
            title=title,
            source_type="hotel_room",
            section="room_type",
            metadata=room_metadata,
            strategy="atomic",
        )
        if chunk:
            chunks.append(chunk)

    for index, faq in enumerate(_list_of_dicts(record.get("faq"))):
        faq_text = join_non_empty([f"Cau hoi: {faq.get('question')}", f"Tra loi: {faq.get('answer')}"])
        faq_metadata = {**base_metadata, "faq_index": index, "faq_category": faq.get("category")}
        chunk = whole_chunk(
            text=faq_text,
            title=title,
            source_type="hotel_faq",
            section="faq",
            metadata=faq_metadata,
            strategy="atomic",
        )
        if chunk:
            chunks.append(chunk)

    return [chunk for chunk in chunks if len(chunk.raw_text) >= config.min_text_chars]


def chunk_reviews(review_bundle: dict[str, Any], config: ChunkingConfig | None = None) -> list[Chunk]:
    config = config or ChunkingConfig()
    title = clean_text(review_bundle.get("hotel_name") or f"hotel_{review_bundle.get('hotel_id', '')}")
    base_metadata = metadata_payload(review_bundle)
    base_metadata.setdefault("hotel_id", review_bundle.get("hotel_id"))
    base_metadata.setdefault("hotel_name", title)
    chunks: list[Chunk] = []
    seen_fingerprints: set[str] = set()

    for index, review in enumerate(_list_of_dicts(review_bundle.get("reviews"))):
        review_text = _render_review(review)
        fingerprint = stable_chunk_id(review_text.lower())
        if fingerprint in seen_fingerprints:
            continue
        seen_fingerprints.add(fingerprint)
        metadata = {
            **base_metadata,
            "review_index": index,
            "review_id": review.get("review_id"),
            "rating": review.get("rating"),
            "rating_text": review.get("rating_text"),
            "date": review.get("date"),
            "guest_type": review.get("reviewer_type"),
            "room_type": review.get("room_type"),
            "lang": review.get("lang"),
        }
        chunk = whole_chunk(
            text=review_text,
            title=title,
            source_type="review",
            section="danh gia",
            metadata=metadata,
            strategy="atomic",
        )
        if chunk and len(chunk.raw_text) >= config.min_text_chars:
            chunks.append(chunk)

    return chunks


def chunk_cms(document: dict[str, Any], config: ChunkingConfig | None = None) -> list[Chunk]:
    config = config or ChunkingConfig()
    title = clean_text(document.get("title") or document.get("name") or document.get("url") or "CMS document")
    text = clean_text(document.get("body") or document.get("text") or document.get("content"))
    metadata = metadata_payload(document)
    metadata.setdefault("document_id", document.get("document_id") or document.get("id") or stable_chunk_id(title))
    metadata.setdefault("title", title)

    chunks: list[Chunk] = []
    sections = split_markdown_sections(text) or [(title, text)]
    for section, body in sections:
        chunks.extend(
            recursive_sentence_chunks(
                text=body,
                title=title,
                source_type="cms",
                section=section,
                metadata=metadata,
                target_tokens=config.cms_child_token_target,
                overlap_tokens=config.child_token_overlap,
            )
        )
    return chunks


def chunk_document(record: dict[str, Any], source_type: str | None = None, config: ChunkingConfig | None = None) -> list[Chunk]:
    detected = source_type or _detect_source_type(record)
    if detected == "review":
        return chunk_reviews(record, config)
    if detected == "cms":
        return chunk_cms(record, config)
    return chunk_hotel(record, config)


def _detect_source_type(record: dict[str, Any]) -> str:
    if "reviews" in record and "hotel_name" in record:
        return "review"
    if any(key in record for key in ("body", "content", "document_id")):
        return "cms"
    return "hotel"


def _render_room(room: dict[str, Any]) -> str:
    fields = [
        room.get("name") or room.get("room_name") or room.get("title"),
        room.get("description"),
        room.get("bed_type"),
        room.get("room_view") or room.get("view"),
    ]
    amenities = room.get("amenities") or room.get("room_amenities") or room.get("facilities")
    if isinstance(amenities, list):
        fields.append("Tien nghi: " + ", ".join(clean_text(item) for item in amenities if clean_text(item)))
    return join_non_empty(fields, separator=". ")


def _render_review(review: dict[str, Any]) -> str:
    return join_non_empty(
        [
            review.get("title"),
            review.get("text"),
            f"Diem tich cuc: {review.get('positives')}" if review.get("positives") else "",
            f"Diem tieu cuc: {review.get('negatives')}" if review.get("negatives") else "",
        ],
        separator="\n",
    )


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [value]
    return []
