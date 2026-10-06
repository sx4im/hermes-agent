"""Auto-detect resolves through the browser provider registry (issue #134152).

``_autodetect_cloud_provider`` must consult ``agent.browser_registry`` — the
same registry the explicit ``browser.cloud_provider`` path uses — so a
plugin listed in ``plugins.disabled`` (which is never registered) cannot be
selected by auto-detect. These tests pin the registry snapshot to simulate
the disabled state and use the real provider classes with env-var-driven
``is_available()``.
"""
from __future__ import annotations

import pytest

from agent import browser_registry
from plugins.browser.browser_use.provider import BrowserUseBrowserProvider
from plugins.browser.browserbase.provider import BrowserbaseBrowserProvider
from tools import browser_tool_cloud as bt_cloud


_BROWSER_ENV_VARS = (
    "BROWSERBASE_API_KEY",
    "BROWSERBASE_PROJECT_ID",
    "BROWSERBASE_BASE_URL",
    "BROWSER_USE_API_KEY",
    "BROWSER_USE_GATEWAY_URL",
    "TOOL_GATEWAY_DOMAIN",
    "TOOL_GATEWAY_USER_TOKEN",
)


@pytest.fixture(autouse=True)
def _clean_browser_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test starts with no browser-provider credentials set."""
    for key in _BROWSER_ENV_VARS:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture(autouse=True)
def _clean_registry():
    """Leave the global provider registry empty after each test."""
    yield
    browser_registry._reset_for_tests()


def _pin_registry(monkeypatch: pytest.MonkeyPatch, *providers) -> None:
    """Register exactly *providers*, simulating ``plugins.disabled``.

    A disabled plugin never registers, so it is absent from the snapshot
    ``_resolve`` walks. Plugin discovery is neutralized for the same reason:
    repopulating the registry here would undo the simulation (discovery
    itself is covered by tests/plugins/browser/test_browser_provider_plugins.py).
    """
    browser_registry._reset_for_tests()
    for provider in providers:
        browser_registry.register_provider(provider)
    monkeypatch.setattr(bt_cloud, "_ensure_browser_plugins_loaded", lambda: None)


def _set_both_available(monkeypatch: pytest.MonkeyPatch) -> None:
    """Credentials present for both providers, so both report available."""
    monkeypatch.setenv("BROWSER_USE_API_KEY", "key")
    monkeypatch.setenv("BROWSERBASE_API_KEY", "key")
    monkeypatch.setenv("BROWSERBASE_PROJECT_ID", "proj")


class TestAutodetectRespectsRegistry:
    def test_autodetect_skips_disabled_plugin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A disabled plugin with credentials present is never auto-detected.

        Regression for #134152: the old code instantiated the provider
        classes directly, so a disabled ``browser-use`` plugin was still
        picked. The registry (which the explicit config path already uses)
        excludes it, so auto-detect must too.
        """
        _pin_registry(monkeypatch, BrowserbaseBrowserProvider())
        _set_both_available(monkeypatch)

        provider = bt_cloud._autodetect_cloud_provider()

        assert provider is not None
        assert provider.name == "browserbase"

    def test_autodetect_prefers_browser_use_when_registered(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Historic preference order (browser-use, then browserbase) is unchanged."""
        _pin_registry(
            monkeypatch, BrowserUseBrowserProvider(), BrowserbaseBrowserProvider()
        )
        _set_both_available(monkeypatch)

        provider = bt_cloud._autodetect_cloud_provider()

        assert provider is not None
        assert provider.name == "browser-use"

    def test_autodetect_returns_none_when_nothing_available(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No registered provider available: auto-detect yields None (local mode)."""
        _pin_registry(
            monkeypatch, BrowserUseBrowserProvider(), BrowserbaseBrowserProvider()
        )

        assert bt_cloud._autodetect_cloud_provider() is None
