"""Tests for gateway configuration parsing (Task 1.8)."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from wechat_clawbot.gateway.config import (
    AccountConfigModel,
    AuthorizationConfig,
    EndpointConfigModel,
    GatewayConfig,
    RoutingConfig,
    load_gateway_config,
    resolve_gateway_state_dir,
    scaffold_gateway_config,
)
from wechat_clawbot.gateway.types import ChannelType

# -- Minimal valid config dict used across multiple tests --------------------


def _minimal_config(**overrides) -> dict:
    """Return a minimal valid config dict, with optional overrides."""
    base = {
        "accounts": {"bot1": {"token": "tok-123"}},
        "endpoints": {"ep1": {"name": "E1", "type": "mcp", "url": "http://localhost:8080"}},
    }
    base.update(overrides)
    return base


class TestResolveGatewayStateDir:
    def test_returns_path(self):
        result = resolve_gateway_state_dir()
        assert isinstance(result, Path)
        assert result == Path.home() / ".clawbot-gateway"


class TestGatewayConfigValidation:
    def test_valid_config(self):
        cfg = GatewayConfig.model_validate(_minimal_config())
        assert "bot1" in cfg.accounts
        assert "ep1" in cfg.endpoints
        assert cfg.endpoints["ep1"].name == "E1"
        assert cfg.endpoints["ep1"].type == ChannelType.MCP

    def test_no_accounts_raises(self):
        with pytest.raises(ValidationError, match="at least one account"):
            GatewayConfig.model_validate({"accounts": {}, "endpoints": {"ep1": {"name": "E1"}}})

    def test_no_endpoints_raises(self):
        with pytest.raises(ValidationError, match="at least one endpoint"):
            GatewayConfig.model_validate({"accounts": {"bot1": {"token": "t"}}, "endpoints": {}})

    def test_missing_accounts_key_raises(self):
        with pytest.raises(ValidationError, match="at least one account"):
            GatewayConfig.model_validate({"endpoints": {"ep1": {"name": "E1"}}})

    def test_missing_endpoints_key_raises(self):
        with pytest.raises(ValidationError, match="at least one endpoint"):
            GatewayConfig.model_validate({"accounts": {"bot1": {"token": "t"}}})


class TestRoutingDefaults:
    def test_defaults(self):
        routing = RoutingConfig()
        assert routing.strategy == "active-endpoint"
        assert routing.mention_prefix == "@"
        assert routing.gateway_commands == ["/"]

    def test_config_routing_defaults(self):
        cfg = GatewayConfig.model_validate(_minimal_config())
        assert cfg.routing.strategy == "active-endpoint"
        assert cfg.routing.mention_prefix == "@"
        assert cfg.routing.gateway_commands == ["/"]


class TestAuthorizationDefaults:
    def test_defaults(self):
        auth = AuthorizationConfig()
        assert auth.mode == "allowlist"
        assert auth.default_endpoints == []
        assert auth.admins == []

    def test_config_authorization_defaults(self):
        cfg = GatewayConfig.model_validate(_minimal_config())
        assert cfg.authorization.mode == "allowlist"
        assert cfg.authorization.default_endpoints == []


class TestScaffoldGatewayConfig:
    def test_creates_file(self, tmp_path):
        result = scaffold_gateway_config(tmp_path)
        assert result.exists()
        assert result.name == "gateway.yaml"
        content = result.read_text(encoding="utf-8")
        assert "accounts:" in content
        assert "endpoints:" in content

    def test_does_not_overwrite(self, tmp_path):
        first = scaffold_gateway_config(tmp_path)
        first.write_text("custom content", encoding="utf-8")
        second = scaffold_gateway_config(tmp_path)
        assert second == first
        assert second.read_text(encoding="utf-8") == "custom content"

    def test_creates_parent_directories(self, tmp_path):
        nested = tmp_path / "a" / "b"
        result = scaffold_gateway_config(nested)
        assert result.exists()


class TestLoadGatewayConfig:
    def test_file_not_found_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="Gateway config not found"):
            load_gateway_config(tmp_path / "nonexistent.yaml")

    def test_load_valid_yaml(self, tmp_path):
        """Write a YAML file and load it (requires pyyaml)."""
        yaml_content = """\
accounts:
  bot1:
    token: "tok-abc"
endpoints:
  ep1:
    name: "Test EP"
    type: mcp
    url: "http://localhost:9090"
routing:
  strategy: active-endpoint
"""
        config_file = tmp_path / "gateway.yaml"
        config_file.write_text(yaml_content, encoding="utf-8")

        try:
            cfg = load_gateway_config(config_file)
        except ImportError:
            pytest.skip("pyyaml not installed")

        assert "bot1" in cfg.accounts
        assert cfg.endpoints["ep1"].name == "Test EP"
        assert cfg.routing.strategy == "active-endpoint"

    def test_load_invalid_yaml_not_mapping(self, tmp_path):
        """YAML that parses to a non-dict should raise ValueError."""
        config_file = tmp_path / "gateway.yaml"
        config_file.write_text("- just\n- a\n- list\n", encoding="utf-8")

        try:
            with pytest.raises(ValueError, match="Expected a YAML mapping"):
                load_gateway_config(config_file)
        except ImportError:
            pytest.skip("pyyaml not installed")

    def test_pydantic_model_directly(self):
        """Test the Pydantic model with a dict (no YAML dependency needed)."""
        cfg = GatewayConfig.model_validate(_minimal_config())
        assert isinstance(cfg.accounts["bot1"], AccountConfigModel)
        assert isinstance(cfg.endpoints["ep1"], EndpointConfigModel)
