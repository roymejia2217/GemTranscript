import logging
from google import genai

logger = logging.getLogger(__name__)


class ModelResolutionError(Exception):
    """Raised when no suitable Gemini Flash model can be resolved."""
    pass


_resolved_model: str | None = None


def _normalize_model_name(raw_name: str) -> str:
    """Strip 'models/' prefix and whitespace from model name."""
    name = raw_name.strip()
    prefix = "models/"
    if name.startswith(prefix):
        name = name[len(prefix):]
    return name


def _get_fallback_list() -> list[str]:
    """Return prioritized fallback Flash model names."""
    return [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-2.0-flash-001",
        "gemini-1.5-flash",
    ]


def _validate_model_exists(api_key: str, model_name: str) -> bool:
    """Check if a specific model exists by calling client.models.get().

    The google-genai SDK does not consistently expose supported_generation_methods,
    so we validate purely by whether the API call succeeds.
    """
    try:
        client = genai.Client(api_key=api_key)
        client.models.get(model=model_name)
        return True
    except Exception:
        return False


def _discover_flash_models(api_key: str) -> list[str]:
    """Discover available Flash models via API.

    Filters by name containing 'flash'. Does not rely on
    supported_generation_methods (not exposed by all SDK versions).
    """
    try:
        client = genai.Client(api_key=api_key)
        flash_models = []
        for model in client.models.list():
            raw_name = getattr(model, "name", "")
            normalized = _normalize_model_name(raw_name)
            if "flash" in normalized.lower():
                flash_models.append(normalized)
        return flash_models
    except Exception as e:
        logger.warning(f"Model discovery failed: {e}")
        return []


def resolve_model(api_key: str, preferred_model: str | None = None) -> str:
    """
    Resolve the best available Gemini Flash model.
    
    Priority:
    1. In-memory cache
    2. User-provided preferred_model (if valid)
    3. Dynamic discovery via client.models.list()
    4. Hardcoded fallback list
    
    Returns bare model name (e.g., "gemini-2.0-flash").
    Raises ModelResolutionError if no model can be resolved.
    """
    global _resolved_model
    
    if _resolved_model is not None:
        return _resolved_model
    
    # Try user override
    if preferred_model:
        normalized = _normalize_model_name(preferred_model)
        if normalized:
            if _validate_model_exists(api_key, normalized):
                logger.info(f"Using user-specified model: {normalized}")
                _resolved_model = normalized
                return normalized
            else:
                logger.warning(f"User-specified model '{normalized}' not found or unsupported. Falling back to discovery.")
    
    # Try dynamic discovery
    discovered = _discover_flash_models(api_key)
    if discovered:
        best = discovered[0]
        logger.info(f"Discovered model via API: {best}")
        _resolved_model = best
        return best
    
    # Try fallback list
    fallback_models = _get_fallback_list()
    attempted = []
    for model in fallback_models:
        attempted.append(model)
        if _validate_model_exists(api_key, model):
            logger.info(f"Using fallback model: {model}")
            _resolved_model = model
            return model
    
    # All failed
    raise ModelResolutionError(
        f"Could not resolve a valid Gemini Flash model. "
        f"Attempted: {attempted}. "
        f"Please check your API key, network connection, or set GEMINI_MODEL_NAME in your .env file."
    )
