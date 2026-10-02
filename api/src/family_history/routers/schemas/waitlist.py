"""The public waitlist."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import StringConstraints, field_validator

from family_history.routers.schemas.common import ApiModel, InputModel, LangTag

_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
_EMAIL = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@" + _LABEL + r"(?:\." + _LABEL + r")+$")

AvisoVersion = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9._-]{1,50}$")]


class WaitlistRequest(InputModel):
    email: Annotated[str, StringConstraints(min_length=3, max_length=254)]
    locale: LangTag = "es-MX"
    consent: bool
    aviso_version: AvisoVersion

    @field_validator("email")
    @classmethod
    def _email_shape(cls, value: str) -> str:
        local, _, domain = value.rpartition("@")
        if not _EMAIL.match(value) or len(local) > 64 or ".." in value:
            raise ValueError("email is not valid")
        return f"{local}@{domain.lower()}"


class WaitlistAccepted(ApiModel):
    status: Literal["accepted"] = "accepted"
