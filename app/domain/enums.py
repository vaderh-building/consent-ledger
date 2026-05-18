"""Enums shared across domain layers.

`UseType` is the granular axis along which artist consent is expressed. A consent
policy declares an allow/deny + optional weight cap for each one separately,
because "is it okay to use my work in AI training?" is the wrong unit of decision —
voice cloning and style conditioning have very different artistic and legal weight.
"""

from __future__ import annotations

from enum import StrEnum


class UseType(StrEnum):
    STYLE_CONDITIONING = "STYLE_CONDITIONING"
    VOICE_CLONING = "VOICE_CLONING"
    STEM_USE = "STEM_USE"
    FULL_TRACK_REFERENCE = "FULL_TRACK_REFERENCE"
    LYRICAL_REFERENCE = "LYRICAL_REFERENCE"


class AuthorizationDecision(StrEnum):
    ALLOW = "ALLOW"
    PARTIAL = "PARTIAL"
    DENY = "DENY"
