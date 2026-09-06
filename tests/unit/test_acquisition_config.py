from __future__ import annotations

from pathlib import Path

import pytest

from frontier.adapters.acquisition.config import load_fetch_policy, load_source_registry
from frontier.domain.source import AcquisitionClass, SignalRole

ROOT = Path(".")


def test_runtime_loads_frozen_source_registry_and_policy() -> None:
    policy = load_fetch_policy(ROOT)
    registry = load_source_registry(ROOT)

    assert policy.policy_profile == "structured-public-v0"
    assert policy.allowed_schemes == ("https",)
    assert policy.max_redirects == 3
    assert set(registry.sources) == {
        "arxiv.cs-ai",
        "cisa.kev",
        "gdelt.frontier",
        "github.ml-repos",
        "hf.models",
        "hn.frontpage",
        "pypi.updates",
    }
    assert (
        str(registry.source_registry_version)
        == "sha256:c95b29078eb002145b75538b947cfb651cc1d5d7f2921b2347cf68b6065115ee"
    )

    pypi = registry.require("pypi.updates")
    assert pypi.finite_window
    assert pypi.endpoint_url == "https://pypi.org/rss/updates.xml"
    assert pypi.etag_support == "SUPPORTED"

    cisa = registry.require("cisa.kev")
    assert not cisa.finite_window
    assert cisa.fallback_semantics == "SAME_AUTHORITY_MIRROR"
    assert cisa.fallback_urls == (
        "https://raw.githubusercontent.com/cisagov/kev-data/develop/"
        "known_exploited_vulnerabilities.json",
    )

    hn = registry.require("hn.frontpage")
    assert hn.contract.acquisition_class is AcquisitionClass.A_AUTHORITATIVE_STRUCTURED
    assert hn.contract.signal_roles == (SignalRole.ATTENTION,)
    assert hn.finite_window

    gdelt = registry.require("gdelt.frontier")
    assert gdelt.contract.acquisition_class is AcquisitionClass.B_OPEN_AGGREGATION
    assert gdelt.contract.signal_roles == (SignalRole.DISCOVERY,)
    assert gdelt.finite_window

    hf = registry.require("hf.models")
    assert hf.contract.acquisition_class is AcquisitionClass.A_AUTHORITATIVE_STRUCTURED
    assert hf.contract.signal_roles == (SignalRole.PRIMARY_EMISSION,)
    assert hf.finite_window
    assert hf.poll_interval_seconds == 60

    arxiv = registry.require("arxiv.cs-ai")
    assert arxiv.contract.acquisition_class is AcquisitionClass.A_AUTHORITATIVE_STRUCTURED
    assert arxiv.contract.signal_roles == (SignalRole.PRIMARY_EMISSION,)
    assert arxiv.contract.transport.value == "ATOM"
    assert arxiv.finite_window
    assert arxiv.poll_interval_seconds == 900

    github = registry.require("github.ml-repos")
    assert github.contract.acquisition_class is AcquisitionClass.A_AUTHORITATIVE_STRUCTURED
    assert github.contract.signal_roles == (SignalRole.BEHAVIORAL, SignalRole.DISCOVERY)
    assert github.finite_window
    assert github.poll_interval_seconds == 900


def test_registry_fails_closed_when_config_root_is_wrong(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_source_registry(tmp_path)
