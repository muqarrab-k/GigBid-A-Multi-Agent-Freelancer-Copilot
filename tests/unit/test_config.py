from pathlib import Path
from typing import Any

import pytest
import yaml

from agent.config import CONFIG_PATH, NODE_NAMES, ConfigError, get_config, load_config


def write_config(tmp_path: Path, raw: dict[str, Any]) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw))
    return path


def raw_config() -> dict[str, Any]:
    raw: dict[str, Any] = yaml.safe_load(CONFIG_PATH.read_text())
    return raw


def test_default_config_loads() -> None:
    cfg = load_config()
    assert cfg.models.active_profile == "open"
    assert cfg.marketplace.mode == "gigsim"
    assert cfg.budgets.max_revisions == 2
    for node in NODE_NAMES:
        assert cfg.profile.node(node).model


def test_cheap_nodes_have_fallback() -> None:
    cfg = load_config()
    for node in ("scout", "risk_assessor", "compliance"):
        assert cfg.profile.node(node).fallback is not None


def test_paths_resolve_from_repo_root() -> None:
    cfg = load_config()
    assert cfg.paths.policy_pack.is_absolute()
    assert cfg.paths.policy_pack.is_dir()


def test_env_overrides_profile_and_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_PROFILE", "paid")
    monkeypatch.setenv("MARKETPLACE_MODE", "upwork")
    cfg = load_config()
    assert cfg.models.active_profile == "paid"
    assert cfg.marketplace.mode == "upwork"
    assert cfg.marketplace.rate_limit == cfg.marketplace.rate_limits.upwork


def test_bad_env_profile_is_clear(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_PROFILE", "nope")
    with pytest.raises(ConfigError, match="active profile 'nope'"):
        load_config()


def test_bad_marketplace_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARKETPLACE_MODE", "fiverr")
    with pytest.raises(ConfigError, match="marketplace.mode"):
        load_config()


def test_get_config_is_cached() -> None:
    assert get_config() is get_config()


def test_missing_open_profile(tmp_path: Path) -> None:
    raw = raw_config()
    del raw["models"]["profiles"]["open"]
    raw["models"]["active_profile"] = "paid"
    with pytest.raises(ConfigError, match="'open' profile is required"):
        load_config(write_config(tmp_path, raw))


def test_unknown_provider(tmp_path: Path) -> None:
    raw = raw_config()
    raw["models"]["profiles"]["open"]["writer"] = {
        "provider": "mystery",
        "model": "x",
        "base_url": "http://x/v1",
    }
    with pytest.raises(ConfigError, match="unknown provider 'mystery'"):
        load_config(write_config(tmp_path, raw))


def test_typo_key_rejected(tmp_path: Path) -> None:
    raw = raw_config()
    raw["budgets"]["max_revison"] = 3
    with pytest.raises(ConfigError, match="max_revison"):
        load_config(write_config(tmp_path, raw))


def test_out_of_range_values(tmp_path: Path) -> None:
    raw = raw_config()
    raw["thresholds"]["minimum_fit_score"] = 1.5
    with pytest.raises(ConfigError, match="minimum_fit_score"):
        load_config(write_config(tmp_path, raw))


def test_threshold_order(tmp_path: Path) -> None:
    raw = raw_config()
    raw["thresholds"]["watch_fit_score"] = 0.9
    with pytest.raises(ConfigError, match="watch_fit_score"):
        load_config(write_config(tmp_path, raw))


def test_unreadable_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="cannot read"):
        load_config(tmp_path / "missing.yaml")


def test_policy_change_is_config_only(tmp_path: Path) -> None:
    raw = raw_config()
    raw["bidding_rules"]["extra"] = {"connects_surcharge_pct": 20}
    cfg = load_config(write_config(tmp_path, raw))
    assert cfg.bidding_rules.extra["connects_surcharge_pct"] == 20
