from .emotion import gate, select_pattern
from .patterns import Utterance, build_emotions, build_patterns, collect_utterances
from .seed import Drive, PersonaSeed, build_seed, overlay_from_profile
from .contract import (
    FidelityReport,
    PersonaContract,
    build_persona_contract,
    check_persona,
    extract_contract_from_payload,
)
from .state import apply_deltas, decay_toward_baseline, deltas_for, describe, detect_triggers
from .style import StyleProfile, StyleReport, check, fingerprint, measure

__all__ = [
    "Utterance",
    "build_emotions",
    "build_patterns",
    "collect_utterances",
    "Drive",
    "PersonaSeed",
    "build_seed",
    "overlay_from_profile",
    "FidelityReport",
    "PersonaContract",
    "build_persona_contract",
    "check_persona",
    "extract_contract_from_payload",
    "apply_deltas",
    "decay_toward_baseline",
    "deltas_for",
    "describe",
    "detect_triggers",
    "StyleProfile",
    "StyleReport",
    "check",
    "fingerprint",
    "measure",
    "gate",
    "select_pattern",
]
