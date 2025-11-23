import hashlib
import uuid
from typing import Any, Literal


def _generate_uuid(page_content: str) -> str:
    """Generate a UUID for a document based on page content."""
    md5_hash = hashlib.md5(page_content.encode()).hexdigest()
    return str(uuid.UUID(md5_hash))


def _format_docs(doc: dict[str, Any]) -> str:
    """Format a single document into a string representation."""
    metadata = doc["metadata"]
    meta = "".join(f" {k}={v!r}" for k, v in metadata.items())
    if meta:
        meta = f" {meta}"
    # contextual_text
    return f"<document{meta}>\nsummary: {doc.get('contextual_text', '')}\n\ndocument: {doc['chunk_text']}</document>"  


def format_docs(docs: list[dict[str, Any]] | None) -> str:
    """Format a list of documents into a string representation."""
    if not docs:
        return "<documents></documents>"
    formatted_docs = "\n\n".join(_format_docs(doc) for doc in docs)
    return f"""<documents>
{formatted_docs}
</documents>"""


def reduce_docs(
    existing: list[dict] | None,
    new: list[dict] | Literal["delete"],
) -> list[dict]:
    """Reduce and process documents based on your custom format.

    Handles your document format and only uses existing IDs.
    No new ID generation.
    """
    if new == "delete":
        return []

    existing_list = list(existing) if existing else []

    # Only handle list of dictionaries (your format)
    if not isinstance(new, list):
        return existing_list

    new_list = []
    existing_ids = set(doc.get("id") for doc in existing_list)

    for item in new:
        if isinstance(item, dict):
            item_id = item.get("id")

            # Only add if ID exists and not already in existing
            if item_id is not None and item_id not in existing_ids:
                new_list.append(item)
                existing_ids.add(item_id)

    return existing_list + new_list
