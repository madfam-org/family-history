"""Opaque keyset cursors for `(sort_name, id)` ordered lists."""

from __future__ import annotations

import base64
import binascii
import json
import uuid

from family_history.errors import APIError

MAX_LIMIT = 100
DEFAULT_LIMIT = 50


def encode_cursor(sort_key: str, row_id: uuid.UUID) -> str:
    raw = json.dumps([sort_key, str(row_id)], separators=(",", ":"), ensure_ascii=False)
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> tuple[str, uuid.UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        if not (isinstance(data, list) and len(data) == 2 and isinstance(data[0], str)):
            raise ValueError("unexpected cursor shape")
        return data[0], uuid.UUID(str(data[1]))
    except (ValueError, UnicodeError, binascii.Error) as exc:
        raise APIError(400, "invalid_cursor", "The pagination cursor is not valid.") from exc
