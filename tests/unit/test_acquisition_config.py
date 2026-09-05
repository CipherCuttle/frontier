from __future__ import annotations

from pathlib import Path

import pytest

from frontier.adapters.acquisition.config import load_fetch_policy, load_source_registry

ROOT = Path(".")


def test_runtime_loads_frozen_pr02_registry_and_policy() -> None:
    policy = load_fetch_policy(ROOT)
    registry = load_source_registry(ROOT)

    assert policy.policy_profile == "structured-public-v0"
    assert policy.allowed_schemes == ("https",)
    assert policy.max_redirects == 3
    assert set(registry.sources) == {"cisa.kev", "pypi.updates"}
    assert (
        str(registry.source_registry_version)
        == "sha256:c0a7653faffbb3827f53e07c10072f31fbb29676ea7c4c35b287c95f77695290"
    )

    pypi = registry.require("pypi.updates")
    assert pypi.finite_window
    assert pypi.endpoint_url == "https://pypi.org/rss/updates.xml"
    assert pypi.etag_support == "SUPPORTED"

    cisa = registry.require("cisa.kev")
    assert not cisa.finite_window
    assert cisa.fallback_semantics == "SAME_AUTHORITY_MIRROR"
    assert cisa.fallback_urls == (
        "https://raw.githubusercontent.com/cisagov/kev-data/develop/known_exploited_vulnerabilities.json",
    )


def test_registry_fails_closed_when_config_root_is_wrong(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_source_registry(tmp_path)
