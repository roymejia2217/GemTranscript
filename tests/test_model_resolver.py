"""
Tests for src/model_resolver.py — dynamic model discovery and fallbacks.

These tests define the interface contract for the ModelResolver module BEFORE
implementation. All tests should FAIL (ImportError/AttributeError) until
src/model_resolver.py is implemented.

Test groups:
  a. _normalize_model_name() — strip prefixes, whitespace, pass-through
  b. _get_fallback_list() — ordered fallback model list
  c. resolve_model() caching — module-level cache behaviour
  d. resolve_model() with user override — preferred_model handling
  e. resolve_model() with dynamic discovery — client.models.list() path
  f. resolve_model() with fallbacks — _validate_model_exists path
  g. _validate_model_exists() — model existence checks
"""

import pytest
import importlib
import sys
from unittest.mock import patch, MagicMock, PropertyMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _import_model_resolver():
    """Import (or re-import) the model_resolver module to pick up changes."""
    if "src.model_resolver" in sys.modules:
        return importlib.reload(sys.modules["src.model_resolver"])
    return importlib.import_module("src.model_resolver")


def _make_model_mock(name, methods=None):
    """
    Create a mock object that mimics a model returned by client.models.list().

    Args:
        name: model name, e.g. "models/gemini-2.0-flash"
        methods: list of supported generation methods, e.g. ["generateContent"]
    """
    m = MagicMock()
    m.name = name
    m.supported_generation_methods = methods or []
    return m


def _make_client_mock(models_list_return=None, models_list_side_effect=None,
                      models_get_return=None, models_get_side_effect=None):
    """
    Create a mock google.genai.Client with configurable models.list and models.get.

    Args:
        models_list_return: iterable of model mocks for client.models.list()
        models_list_side_effect: exception to raise on client.models.list()
        models_get_return: model mock for client.models.get(model=...)
        models_get_side_effect: exception to raise on client.models.get()
    """
    client = MagicMock()
    if models_list_side_effect is not None:
        client.models.list.side_effect = models_list_side_effect
    else:
        client.models.list.return_value = models_list_return or []

    if models_get_side_effect is not None:
        client.models.get.side_effect = models_get_side_effect
    else:
        client.models.get.return_value = models_get_return or MagicMock()
    return client


# ===========================================================================
# a. _normalize_model_name()
# ===========================================================================

class TestNormalizeModelName:
    """Verify _normalize_model_name strips 'models/' prefix and whitespace."""

    def test_strip_models_prefix(self):
        """'models/gemini-2.0-flash' → 'gemini-2.0-flash'"""
        mr = _import_model_resolver()
        assert mr._normalize_model_name("models/gemini-2.0-flash") == "gemini-2.0-flash"

    def test_strip_whitespace(self):
        """'  gemini-2.0-flash  ' → 'gemini-2.0-flash'"""
        mr = _import_model_resolver()
        assert mr._normalize_model_name("  gemini-2.0-flash  ") == "gemini-2.0-flash"

    def test_bare_name_unchanged(self):
        """'gemini-2.0-flash' should pass through unchanged."""
        mr = _import_model_resolver()
        assert mr._normalize_model_name("gemini-2.0-flash") == "gemini-2.0-flash"

    def test_prefix_and_whitespace_combined(self):
        """'  models/gemini-2.0-flash  ' → 'gemini-2.0-flash'"""
        mr = _import_model_resolver()
        assert mr._normalize_model_name("  models/gemini-2.0-flash  ") == "gemini-2.0-flash"

    def test_empty_string(self):
        """Empty string should return empty string."""
        mr = _import_model_resolver()
        assert mr._normalize_model_name("") == ""

    def test_only_prefix(self):
        """'models/' with no model name should return empty string."""
        mr = _import_model_resolver()
        assert mr._normalize_model_name("models/") == ""

    def test_nested_prefix_stripped_once(self):
        """'models/models/gemini-2.0-flash' — only the first 'models/' is stripped."""
        mr = _import_model_resolver()
        # After stripping "models/" once, result is "models/gemini-2.0-flash"
        # The function should only strip one prefix, not recursively
        result = mr._normalize_model_name("models/models/gemini-2.0-flash")
        assert result == "models/gemini-2.0-flash"


# ===========================================================================
# b. _get_fallback_list()
# ===========================================================================

class TestGetFallbackList:
    """Verify _get_fallback_list returns the correct ordered list."""

    EXPECTED_FALLBACKS = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-2.0-flash-001",
        "gemini-1.5-flash",
    ]

    def test_returns_list(self):
        """_get_fallback_list() should return a list."""
        mr = _import_model_resolver()
        result = mr._get_fallback_list()
        assert isinstance(result, list)

    def test_returns_correct_order(self):
        """Fallback list must match the planned order exactly."""
        mr = _import_model_resolver()
        result = mr._get_fallback_list()
        assert result == self.EXPECTED_FALLBACKS

    def test_contains_expected_models(self):
        """Each expected model must be present in the fallback list."""
        mr = _import_model_resolver()
        result = mr._get_fallback_list()
        for model in self.EXPECTED_FALLBACKS:
            assert model in result, f"Expected {model!r} in fallback list"

    def test_non_empty(self):
        """Fallback list must not be empty."""
        mr = _import_model_resolver()
        result = mr._get_fallback_list()
        assert len(result) > 0

    def test_all_strings(self):
        """Every entry in the fallback list must be a string."""
        mr = _import_model_resolver()
        result = mr._get_fallback_list()
        assert all(isinstance(m, str) for m in result)


# ===========================================================================
# c. resolve_model() caching
# ===========================================================================

class TestResolveModelCaching:
    """Verify module-level caching: second call returns cached value without API calls."""

    def test_first_call_hits_api(self):
        """First call to resolve_model should invoke the API (discovery or validation)."""
        mr = _import_model_resolver()
        # Reset cache
        mr._resolved_model = None

        mock_client = _make_client_mock(
            models_list_return=[
                _make_model_mock("models/gemini-2.0-flash", ["generateContent"])
            ]
        )

        with patch("src.model_resolver.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            result = mr.resolve_model("test-api-key")

        assert result is not None
        # The Client should have been constructed at least once
        assert mock_genai.Client.call_count >= 1

    def test_second_call_returns_cached_value(self):
        """Second call should return the same model without creating a new Client."""
        mr = _import_model_resolver()
        # Reset cache
        mr._resolved_model = None

        mock_client = _make_client_mock(
            models_list_return=[
                _make_model_mock("models/gemini-2.0-flash", ["generateContent"])
            ]
        )

        with patch("src.model_resolver.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            result1 = mr.resolve_model("test-api-key")
            result2 = mr.resolve_model("test-api-key")

        assert result1 == result2
        # Client should only be constructed once (first call)
        assert mock_genai.Client.call_count == 1

    def test_cache_is_module_level(self):
        """The cache (_resolved_model) should be a module-level variable."""
        mr = _import_model_resolver()
        assert hasattr(mr, "_resolved_model"), "Module must have _resolved_model attribute"

    def test_cache_can_be_cleared(self):
        """Setting _resolved_model = None should force a fresh resolution on next call."""
        mr = _import_model_resolver()
        mr._resolved_model = None

        mock_client = _make_client_mock(
            models_list_return=[
                _make_model_mock("models/gemini-2.0-flash", ["generateContent"])
            ]
        )

        with patch("src.model_resolver.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            result1 = mr.resolve_model("test-api-key")

        # Clear cache
        mr._resolved_model = None

        with patch("src.model_resolver.genai") as mock_genai2:
            mock_genai2.Client.return_value = mock_client
            result2 = mr.resolve_model("test-api-key")

        # Both calls should produce valid results
        assert result1 is not None
        assert result2 is not None


# ===========================================================================
# d. resolve_model() with user override (preferred_model)
# ===========================================================================

class TestResolveModelUserOverride:
    """Verify preferred_model handling in resolve_model()."""

    def setup_method(self):
        """Clear cache before each test."""
        mr = _import_model_resolver()
        mr._resolved_model = None

    def test_valid_preferred_model_used_directly(self):
        """When preferred_model is valid and exists, it should be used without discovery."""
        mr = _import_model_resolver()
        mr._resolved_model = None

        mock_client = _make_client_mock(
            models_get_return=_make_model_mock("models/gemini-2.5-flash", ["generateContent"])
        )

        with patch("src.model_resolver.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            result = mr.resolve_model("test-api-key", preferred_model="gemini-2.5-flash")

        assert result == "gemini-2.5-flash"

    def test_preferred_model_with_models_prefix_normalized(self):
        """preferred_model='models/gemini-2.5-flash' should be normalized to 'gemini-2.5-flash'."""
        mr = _import_model_resolver()
        mr._resolved_model = None

        mock_client = _make_client_mock(
            models_get_return=_make_model_mock("models/gemini-2.5-flash", ["generateContent"])
        )

        with patch("src.model_resolver.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            result = mr.resolve_model("test-api-key", preferred_model="models/gemini-2.5-flash")

        assert result == "gemini-2.5-flash"

    def test_empty_preferred_model_treated_as_none(self):
        """preferred_model='' should be treated as None, triggering discovery."""
        mr = _import_model_resolver()
        mr._resolved_model = None

        mock_client = _make_client_mock(
            models_list_return=[
                _make_model_mock("models/gemini-2.0-flash", ["generateContent"])
            ]
        )

        with patch("src.model_resolver.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            result = mr.resolve_model("test-api-key", preferred_model="")

        # Should fall through to discovery, not use empty string
        assert result is not None
        assert result != ""

    def test_whitespace_preferred_model_treated_as_none(self):
        """preferred_model='   ' should be treated as None, triggering discovery."""
        mr = _import_model_resolver()
        mr._resolved_model = None

        mock_client = _make_client_mock(
            models_list_return=[
                _make_model_mock("models/gemini-2.0-flash", ["generateContent"])
            ]
        )

        with patch("src.model_resolver.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            result = mr.resolve_model("test-api-key", preferred_model="   ")

        assert result is not None
        assert result.strip() != ""

    def test_invalid_preferred_model_falls_through_to_discovery(self):
        """When preferred_model doesn't exist, should fall through to discovery."""
        mr = _import_model_resolver()
        mr._resolved_model = None

        # Validation of preferred model fails
        mock_client = _make_client_mock()
        mock_client.models.get.side_effect = Exception("Model not found")
        # But discovery succeeds
        mock_client.models.list.return_value = [
            _make_model_mock("models/gemini-2.0-flash", ["generateContent"])
        ]

        with patch("src.model_resolver.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            result = mr.resolve_model("test-api-key", preferred_model="nonexistent-model")

        # Should fall through to discovery and find a flash model
        assert result is not None
        assert "flash" in result

    def test_preferred_model_is_cached(self):
        """A valid preferred_model should be cached for subsequent calls."""
        mr = _import_model_resolver()
        mr._resolved_model = None

        mock_client = _make_client_mock(
            models_get_return=_make_model_mock("models/gemini-2.5-flash", ["generateContent"])
        )

        with patch("src.model_resolver.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            result1 = mr.resolve_model("test-api-key", preferred_model="gemini-2.5-flash")

        # Second call should use cache
        result2 = mr.resolve_model("test-api-key", preferred_model="gemini-2.5-flash")
        assert result1 == result2
        assert result1 == "gemini-2.5-flash"


# ===========================================================================
# e. resolve_model() with dynamic discovery
# ===========================================================================

class TestResolveModelDynamicDiscovery:
    """Verify dynamic model discovery via client.models.list()."""

    def setup_method(self):
        """Clear cache before each test."""
        mr = _import_model_resolver()
        mr._resolved_model = None

    def test_discovery_finds_flash_model_with_generate_content(self):
        """client.models.list() returns Flash models with generateContent → pick best."""
        mr = _import_model_resolver()
        mr._resolved_model = None

        mock_client = _make_client_mock(
            models_list_return=[
                _make_model_mock("models/gemini-1.5-flash", ["generateContent"]),
                _make_model_mock("models/gemini-2.0-flash", ["generateContent"]),
            ]
        )

        with patch("src.model_resolver.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            result = mr.resolve_model("test-api-key")

        assert result is not None
        assert "flash" in result

    def test_discovery_no_flash_models_falls_to_fallback(self):
        """client.models.list() returns no Flash models → fall to fallback list."""
        mr = _import_model_resolver()
        mr._resolved_model = None

        mock_client = _make_client_mock(
            models_list_return=[
                _make_model_mock("models/gemini-2.0-pro", ["generateContent"]),
            ]
        )
        # Make models.get succeed for the first fallback model
        mock_client.models.get.return_value = _make_model_mock(
            "models/gemini-2.5-flash", ["generateContent"]
        )

        with patch("src.model_resolver.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            result = mr.resolve_model("test-api-key")

        # Should fall to fallback list and return a model from it
        assert result is not None

    def test_discovery_returns_all_flash_models(self):
        """Flash models are returned regardless of supported_generation_methods."""
        mr = _import_model_resolver()
        mr._resolved_model = None

        mock_client = _make_client_mock(
            models_list_return=[
                _make_model_mock("models/gemini-2.0-flash", ["embedContent"]),
            ]
        )

        with patch("src.model_resolver.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            result = mr.resolve_model("test-api-key")

        # Discovered flash model should be used even without generateContent in methods list
        assert result is not None
        assert "flash" in result

    def test_discovery_network_error_falls_to_fallback(self):
        """client.models.list() raises exception → fall to fallback list."""
        mr = _import_model_resolver()
        mr._resolved_model = None

        mock_client = _make_client_mock(
            models_list_side_effect=Exception("Network timeout")
        )
        # Fallback validation succeeds
        mock_client.models.get.return_value = _make_model_mock(
            "models/gemini-2.5-flash", ["generateContent"]
        )

        with patch("src.model_resolver.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            result = mr.resolve_model("test-api-key")

        # Should fall to fallback
        assert result is not None

    def test_discovery_picks_newest_flash_model(self):
        """When multiple Flash models are discovered, the best/newest should be picked."""
        mr = _import_model_resolver()
        mr._resolved_model = None

        mock_client = _make_client_mock(
            models_list_return=[
                _make_model_mock("models/gemini-1.5-flash", ["generateContent"]),
                _make_model_mock("models/gemini-2.0-flash", ["generateContent"]),
                _make_model_mock("models/gemini-2.5-flash", ["generateContent"]),
            ]
        )

        with patch("src.model_resolver.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            result = mr.resolve_model("test-api-key")

        # The result should be one of the flash models (newest preferred)
        assert result is not None
        assert "flash" in result
        # The newest model (2.5) should be preferred over older ones
        assert result in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]


# ===========================================================================
# f. resolve_model() with fallbacks
# ===========================================================================

class TestResolveModelFallbacks:
    """Verify fallback list resolution when discovery fails or is skipped."""

    def setup_method(self):
        """Clear cache before each test."""
        mr = _import_model_resolver()
        mr._resolved_model = None

    def test_first_fallback_valid_returned(self):
        """When the first fallback model is valid, it should be returned and cached."""
        mr = _import_model_resolver()
        mr._resolved_model = None

        # Discovery returns nothing useful
        mock_client = _make_client_mock(models_list_return=[])
        # First fallback model is valid
        mock_client.models.get.return_value = _make_model_mock(
            "models/gemini-2.5-flash", ["generateContent"]
        )

        with patch("src.model_resolver.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            result = mr.resolve_model("test-api-key")

        assert result == "gemini-2.5-flash"

    def test_all_fallbacks_invalid_raises_error(self):
        """When all fallback models are invalid, ModelResolutionError should be raised."""
        mr = _import_model_resolver()
        mr._resolved_model = None

        # Discovery returns nothing
        mock_client = _make_client_mock(models_list_return=[])
        # All fallback validations fail
        mock_client.models.get.side_effect = Exception("Model not found")

        with patch("src.model_resolver.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            with pytest.raises(mr.ModelResolutionError):
                mr.resolve_model("test-api-key")

    def test_error_message_lists_attempted_models(self):
        """ModelResolutionError message should list the models that were attempted."""
        mr = _import_model_resolver()
        mr._resolved_model = None

        # Discovery returns nothing
        mock_client = _make_client_mock(models_list_return=[])
        # All fallback validations fail
        mock_client.models.get.side_effect = Exception("Model not found")

        with patch("src.model_resolver.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            with pytest.raises(mr.ModelResolutionError) as exc_info:
                mr.resolve_model("test-api-key")

        error_msg = str(exc_info.value)
        # The error should mention that models were attempted
        assert len(error_msg) > 0

    def test_second_fallback_used_when_first_invalid(self):
        """When the first fallback is invalid, the second should be tried."""
        mr = _import_model_resolver()
        mr._resolved_model = None

        # Discovery returns nothing
        mock_client = _make_client_mock(models_list_return=[])

        # First fallback invalid, second valid
        call_count = [0]

        def get_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("Model not found")
            return _make_model_mock("models/gemini-2.0-flash", ["generateContent"])

        mock_client.models.get.side_effect = get_side_effect

        with patch("src.model_resolver.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            result = mr.resolve_model("test-api-key")

        # Should have gotten a model from the fallback list
        assert result is not None

    def test_fallback_result_is_cached(self):
        """A model found via fallback should be cached for subsequent calls."""
        mr = _import_model_resolver()
        mr._resolved_model = None

        # Discovery returns nothing
        mock_client = _make_client_mock(models_list_return=[])
        mock_client.models.get.return_value = _make_model_mock(
            "models/gemini-2.5-flash", ["generateContent"]
        )

        with patch("src.model_resolver.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            result1 = mr.resolve_model("test-api-key")

        # Second call should use cache, no new Client needed
        result2 = mr.resolve_model("test-api-key")
        assert result1 == result2


# ===========================================================================
# g. _validate_model_exists()
# ===========================================================================

class TestValidateModelExists:
    """Verify _validate_model_exists checks model existence via the API."""

    def setup_method(self):
        """Clear cache before each test."""
        mr = _import_model_resolver()
        mr._resolved_model = None

    def test_valid_model_returns_true(self):
        """A model that exists should return True."""
        mr = _import_model_resolver()

        mock_client = _make_client_mock(
            models_get_return=_make_model_mock("models/gemini-2.0-flash", ["generateContent"])
        )

        with patch("src.model_resolver.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            result = mr._validate_model_exists("test-api-key", "gemini-2.0-flash")

        assert result is True

    def test_invalid_model_returns_false(self):
        """A model that doesn't exist should return False (not raise)."""
        mr = _import_model_resolver()

        mock_client = _make_client_mock()
        mock_client.models.get.side_effect = Exception("Not found")

        with patch("src.model_resolver.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            result = mr._validate_model_exists("test-api-key", "nonexistent-model")

        assert result is False

    def test_handles_exceptions_gracefully(self):
        """Network errors or other exceptions should return False, not propagate."""
        mr = _import_model_resolver()

        mock_client = _make_client_mock()
        mock_client.models.get.side_effect = ConnectionError("Network error")

        with patch("src.model_resolver.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            result = mr._validate_model_exists("test-api-key", "gemini-2.0-flash")

        assert result is False


# ===========================================================================
# h. ModelResolutionError
# ===========================================================================

class TestModelResolutionError:
    """Verify ModelResolutionError is a proper exception class."""

    def test_is_exception_subclass(self):
        """ModelResolutionError should be a subclass of Exception."""
        mr = _import_model_resolver()
        assert issubclass(mr.ModelResolutionError, Exception)

    def test_can_be_raised_and_caught(self):
        """ModelResolutionError should be raisable and catchable."""
        mr = _import_model_resolver()
        with pytest.raises(mr.ModelResolutionError):
            raise mr.ModelResolutionError("No models available")

    def test_error_message_preserved(self):
        """The error message should be preserved."""
        mr = _import_model_resolver()
        try:
            raise mr.ModelResolutionError("No models available")
        except mr.ModelResolutionError as e:
            assert "No models available" in str(e)


# ===========================================================================
# i. _discover_flash_models()
# ===========================================================================

class TestDiscoverFlashModels:
    """Verify _discover_flash_models filters and returns Flash models with generateContent."""

    def setup_method(self):
        """Clear cache before each test."""
        mr = _import_model_resolver()
        mr._resolved_model = None

    def test_returns_flash_models_with_generate_content(self):
        """Should return only Flash models that support generateContent."""
        mr = _import_model_resolver()

        mock_client = _make_client_mock(
            models_list_return=[
                _make_model_mock("models/gemini-2.0-flash", ["generateContent"]),
                _make_model_mock("models/gemini-2.0-pro", ["generateContent"]),
                _make_model_mock("models/gemini-1.5-flash", ["generateContent"]),
            ]
        )

        with patch("src.model_resolver.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            result = mr._discover_flash_models("test-api-key")

        # Only flash models should be returned
        assert all("flash" in m for m in result)
        assert len(result) == 2

    def test_returns_all_flash_models_regardless_of_methods(self):
        """All Flash models are returned; we no longer filter by supported_generation_methods."""
        mr = _import_model_resolver()

        mock_client = _make_client_mock(
            models_list_return=[
                _make_model_mock("models/gemini-2.0-flash", ["embedContent"]),
                _make_model_mock("models/gemini-1.5-flash", ["generateContent"]),
            ]
        )

        with patch("src.model_resolver.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            result = mr._discover_flash_models("test-api-key")

        # Both flash models should be returned regardless of methods
        assert len(result) == 2
        assert all("flash" in m for m in result)

    def test_returns_empty_list_on_api_error(self):
        """When client.models.list() raises, should return empty list."""
        mr = _import_model_resolver()

        mock_client = _make_client_mock(
            models_list_side_effect=Exception("API error")
        )

        with patch("src.model_resolver.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            result = mr._discover_flash_models("test-api-key")

        assert result == []

    def test_returns_empty_list_when_no_flash_models(self):
        """When no Flash models are found, should return empty list."""
        mr = _import_model_resolver()

        mock_client = _make_client_mock(
            models_list_return=[
                _make_model_mock("models/gemini-2.0-pro", ["generateContent"]),
            ]
        )

        with patch("src.model_resolver.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            result = mr._discover_flash_models("test-api-key")

        assert result == []

    def test_model_names_are_normalized(self):
        """Returned model names should have 'models/' prefix stripped."""
        mr = _import_model_resolver()

        mock_client = _make_client_mock(
            models_list_return=[
                _make_model_mock("models/gemini-2.0-flash", ["generateContent"]),
            ]
        )

        with patch("src.model_resolver.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            result = mr._discover_flash_models("test-api-key")

        for model_name in result:
            assert not model_name.startswith("models/"), \
                f"Model name {model_name!r} should not have 'models/' prefix"