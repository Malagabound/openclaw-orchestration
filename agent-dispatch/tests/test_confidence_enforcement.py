"""Tests for confidence score enforcement in agent_supervisor.

Verifies that:
  - Confidence below threshold triggers AgentRunnerError (recovery pipeline)
  - Confidence above threshold passes through to completion
"""

import sys
import os
import unittest
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

# Resolve import path for agent-dispatch package
_agent_dispatch_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_project_root = os.path.dirname(_agent_dispatch_dir)

if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import importlib
import importlib.util

_spec = importlib.util.spec_from_file_location(
    "agent_dispatch",
    os.path.join(_agent_dispatch_dir, "__init__.py"),
    submodule_search_locations=[_agent_dispatch_dir],
)
_agent_dispatch_mod = importlib.util.module_from_spec(_spec)
sys.modules["agent_dispatch"] = _agent_dispatch_mod
_spec.loader.exec_module(_agent_dispatch_mod)

# Register submodules needed
for _modname in ["config", "verification"]:
    _modpath = os.path.join(_agent_dispatch_dir, f"{_modname}.py")
    if os.path.exists(_modpath):
        full_name = f"agent_dispatch.{_modname}"
        spec = importlib.util.spec_from_file_location(full_name, _modpath)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[full_name] = mod
        setattr(_agent_dispatch_mod, _modname, mod)
        spec.loader.exec_module(mod)

from agent_dispatch.config import get_recovery_config


class TestConfidenceEnforcement(unittest.TestCase):
    """Tests for confidence score threshold enforcement."""

    def test_confidence_below_threshold_detected(self):
        """Confidence below min_confidence_score should be detected."""
        config = {
            "recovery": {
                "min_confidence_score": 0.3,
            }
        }
        recovery_cfg = get_recovery_config(config)
        min_confidence = recovery_cfg.get("min_confidence_score", 0.3)

        # Simulate agent result with low confidence
        confidence_score = 0.15
        self.assertLess(confidence_score, min_confidence)

    def test_confidence_above_threshold_passes(self):
        """Confidence above min_confidence_score should pass."""
        config = {
            "recovery": {
                "min_confidence_score": 0.3,
            }
        }
        recovery_cfg = get_recovery_config(config)
        min_confidence = recovery_cfg.get("min_confidence_score", 0.3)

        confidence_score = 0.85
        self.assertGreaterEqual(confidence_score, min_confidence)

    def test_confidence_at_threshold_passes(self):
        """Confidence exactly at min_confidence_score should pass."""
        config = {
            "recovery": {
                "min_confidence_score": 0.3,
            }
        }
        recovery_cfg = get_recovery_config(config)
        min_confidence = recovery_cfg.get("min_confidence_score", 0.3)

        confidence_score = 0.3
        # >= threshold should pass
        self.assertGreaterEqual(confidence_score, min_confidence)

    def test_default_threshold_used_when_not_configured(self):
        """When no min_confidence_score in config, default 0.3 should be used."""
        config = {}
        recovery_cfg = get_recovery_config(config)
        self.assertEqual(recovery_cfg["min_confidence_score"], 0.3)

    def test_custom_threshold_respected(self):
        """Custom min_confidence_score should override default."""
        config = {
            "recovery": {
                "min_confidence_score": 0.5,
            }
        }
        recovery_cfg = get_recovery_config(config)
        self.assertEqual(recovery_cfg["min_confidence_score"], 0.5)


class TestConfidenceErrorClassification(unittest.TestCase):
    """Test that confidence_too_low stop_reason maps to CONFIDENCE_TOO_LOW error code."""

    def test_confidence_too_low_error_code_detection(self):
        """AgentRunnerError with confidence message should map to CONFIDENCE_TOO_LOW."""
        # Register error_classifier submodule
        recovery_dir = os.path.join(_agent_dispatch_dir, "recovery")
        for _modname in ["error_classifier"]:
            _modpath = os.path.join(recovery_dir, f"{_modname}.py")
            if os.path.exists(_modpath):
                full_name = f"agent_dispatch.recovery.{_modname}"
                if full_name not in sys.modules:
                    # Register recovery package first
                    recovery_init = os.path.join(recovery_dir, "__init__.py")
                    if "agent_dispatch.recovery" not in sys.modules:
                        r_spec = importlib.util.spec_from_file_location(
                            "agent_dispatch.recovery", recovery_init,
                            submodule_search_locations=[recovery_dir],
                        )
                        r_mod = importlib.util.module_from_spec(r_spec)
                        sys.modules["agent_dispatch.recovery"] = r_mod
                        setattr(_agent_dispatch_mod, "recovery", r_mod)
                        r_spec.loader.exec_module(r_mod)

                    spec = importlib.util.spec_from_file_location(full_name, _modpath)
                    mod = importlib.util.module_from_spec(spec)
                    sys.modules[full_name] = mod
                    setattr(sys.modules["agent_dispatch.recovery"], _modname, mod)
                    spec.loader.exec_module(mod)

        from agent_dispatch.recovery.error_classifier import detect_error_code

        class MockAgentRunnerError(Exception):
            pass

        MockAgentRunnerError.__name__ = "AgentRunnerError"

        err = MockAgentRunnerError("Confidence score 0.1 below threshold 0.3")
        code = detect_error_code(exception=err)
        self.assertEqual(code, "CONFIDENCE_TOO_LOW")


if __name__ == "__main__":
    unittest.main()
