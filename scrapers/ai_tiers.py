"""Shared local-model tier configuration for the optional AI scrapers."""

import os

_validated_models = set()


AI_TIERS = ("none", "low", "medium", "high")
DEFAULT_AI_TIER = "none"

ENGINE_MODELS = {
    "low": "qwen3-vl:2b",
    "medium": "llama3.1:8b",
    "high": "llama3.1:70b",
}

CIRCUIT_PRIMARY_MODELS = {
    "low": "qwen3-vl:2b",
    "medium": "qwen3-vl:4b",
    "high": "qwen3-vl:8b",
}

CIRCUIT_ARBITER_MODELS = {
    "medium": "openbmb/minicpm-v4.6:1b",
    "high": "openbmb/minicpm-v4.6:1b",
}


def resolve_ai_tier(tier=None):
    """Resolve and validate F1_AI_TIER, defaulting to the no-AI path."""
    resolved = (tier if tier is not None else os.getenv("F1_AI_TIER", DEFAULT_AI_TIER)).strip().lower()
    if resolved not in AI_TIERS:
        expected = ", ".join(AI_TIERS)
        raise ValueError(f"Unsupported F1_AI_TIER {resolved!r}; expected one of: {expected}.")
    return resolved


def require_ollama_models(*model_names):
    """Fail early with setup instructions if Ollama or a requested model is missing."""
    model_names = set(model_names) - _validated_models
    if not model_names:
        return

    try:
        import ollama
    except ImportError as exc:
        raise RuntimeError(
            "This F1_AI_TIER requires the Ollama Python package. Install it and retry."
        ) from exc

    try:
        response = ollama.list()
    except Exception as exc:
        raise RuntimeError(
            "Could not contact the local Ollama service required by F1_AI_TIER. "
            "Start Ollama and retry."
        ) from exc

    listed_models = response.get("models", []) if isinstance(response, dict) else response.models
    installed = set()
    for model in listed_models:
        if isinstance(model, dict):
            name = model.get("model") or model.get("name")
        else:
            name = getattr(model, "model", None) or getattr(model, "name", None)
        if name:
            installed.add(name)

    missing = sorted(set(model_names) - installed)
    if missing:
        pulls = "\n".join(f"  ollama pull {name}" for name in missing)
        raise RuntimeError(
            "The selected F1_AI_TIER requires Ollama model(s) that are not installed:\n"
            f"{pulls}"
        )
    _validated_models.update(model_names)
