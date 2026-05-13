"""Tests for ``opencoat_runtime_daemon.build_runtime`` (M4 PR-17)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from opencoat_runtime_core import OpenCOATRuntime
from opencoat_runtime_core.llm import StubLLMClient
from opencoat_runtime_daemon import build_runtime
from opencoat_runtime_daemon.config.loader import (
    DaemonConfig,
    IPCEndpoint,
    IPCSettings,
    LLMSettings,
    ObservabilitySettings,
    PluginSettings,
    StorageBackend,
    StorageSettings,
    load_config,
)
from opencoat_runtime_protocol import (
    Advice,
    AdviceType,
    Concern,
    JoinpointEvent,
    Pointcut,
    WeavingLevel,
    WeavingOperation,
    WeavingPolicy,
)
from opencoat_runtime_protocol.envelopes import PointcutMatch
from opencoat_runtime_storage.memory import MemoryConcernStore, MemoryDCNStore
from opencoat_runtime_storage.sqlite import SqliteConcernStore, SqliteDCNStore


def _bare_config(
    *,
    concern: StorageBackend,
    dcn: StorageBackend,
    llm: LLMSettings,
) -> DaemonConfig:
    return DaemonConfig(
        storage=StorageSettings(concern_store=concern, dcn_store=dcn),
        llm=llm,
        ipc=IPCSettings(inproc=IPCEndpoint(enabled=True)),
        observability=ObservabilitySettings(),
        plugins=PluginSettings(),
    )


def _concern() -> Concern:
    return Concern(
        id="c-builder",
        name="Builder smoke",
        description="hermetic concern for the builder tests",
        pointcut=Pointcut(match=PointcutMatch(any_keywords=["refund"])),
        advice=Advice(type=AdviceType.REASONING_GUIDANCE, content="be kind"),
        weaving_policy=WeavingPolicy(
            mode=WeavingOperation.INSERT,
            level=WeavingLevel.PROMPT_LEVEL,
            target="reasoning.hints",
            priority=0.5,
        ),
    )


def _joinpoint() -> JoinpointEvent:
    return JoinpointEvent(
        id="jp-build",
        level=2,
        name="before_response",
        host="builder-test",
        agent_session_id="sess",
        ts=datetime(2026, 5, 11, 12, 0, tzinfo=UTC),
        payload={"text": "refund please", "raw_text": "refund please"},
    )


class TestDefaults:
    def test_default_config_yields_memory_and_stub(self) -> None:
        with build_runtime(load_config(), env={}) as built:
            assert isinstance(built.runtime, OpenCOATRuntime)
            assert isinstance(built.runtime.concern_store, MemoryConcernStore)
            assert isinstance(built.runtime.dcn_store, MemoryDCNStore)
            assert built.llm_label == "stub"
            assert isinstance(built.runtime._llm, StubLLMClient)  # type: ignore[attr-defined]

    def test_close_is_idempotent_on_memory(self) -> None:
        built = build_runtime(load_config(), env={})
        built.close()
        built.close()


class TestStorageSqlite:
    def test_sqlite_concern_and_dcn_round_trip(self, tmp_path: Path) -> None:
        db = tmp_path / "state.db"
        cfg = _bare_config(
            concern=StorageBackend(kind="sqlite", path=str(db)),
            dcn=StorageBackend(kind="sqlite", path=str(db)),
            llm=LLMSettings(provider="stub"),
        )

        c = _concern()
        with build_runtime(cfg, env={}) as built:
            assert isinstance(built.runtime.concern_store, SqliteConcernStore)
            assert isinstance(built.runtime.dcn_store, SqliteDCNStore)
            built.runtime.concern_store.upsert(c)

        with build_runtime(cfg, env={}) as built2:
            assert built2.runtime.concern_store.get("c-builder") is not None
            inj = built2.runtime.on_joinpoint(_joinpoint())
            assert inj is not None
            assert any(i.concern_id == "c-builder" for i in inj.injections)

    def test_close_releases_sqlite_handles(self, tmp_path: Path) -> None:
        db = tmp_path / "state.db"
        cfg = _bare_config(
            concern=StorageBackend(kind="sqlite", path=str(db)),
            dcn=StorageBackend(kind="sqlite", path=str(db)),
            llm=LLMSettings(provider="stub"),
        )
        built = build_runtime(cfg, env={})
        built.close()
        with pytest.raises(Exception):
            built.runtime.concern_store.get("c-builder")

    def test_unknown_storage_kind_raises(self) -> None:
        cfg = _bare_config(
            concern=StorageBackend(kind="postgres"),
            dcn=StorageBackend(kind="memory"),
            llm=LLMSettings(provider="stub"),
        )
        with pytest.raises(ValueError, match="concern_store backend"):
            build_runtime(cfg, env={})


class TestLLM:
    def test_unknown_provider_raises(self) -> None:
        cfg = _bare_config(
            concern=StorageBackend(kind="memory"),
            dcn=StorageBackend(kind="memory"),
            llm=LLMSettings(provider="not-a-thing"),
        )
        with pytest.raises(ValueError, match=r"llm\.provider"):
            build_runtime(cfg, env={})

    def test_openai_uses_injected_env_credentials(self) -> None:
        cfg = _bare_config(
            concern=StorageBackend(kind="memory"),
            dcn=StorageBackend(kind="memory"),
            llm=LLMSettings(provider="openai"),
        )
        with build_runtime(cfg, env={"OPENAI_API_KEY": "sk-fake-builder"}) as built:
            assert built.llm_label.startswith("openai/")
            assert not isinstance(built.runtime._llm, StubLLMClient)  # type: ignore[attr-defined]

    def test_anthropic_uses_injected_env_credentials(self) -> None:
        cfg = _bare_config(
            concern=StorageBackend(kind="memory"),
            dcn=StorageBackend(kind="memory"),
            llm=LLMSettings(provider="anthropic"),
        )
        with build_runtime(cfg, env={"ANTHROPIC_API_KEY": "sk-ant-fake"}) as built:
            assert built.llm_label.startswith("anthropic/")
            assert not isinstance(built.runtime._llm, StubLLMClient)  # type: ignore[attr-defined]

    def test_azure_requires_deployment(self) -> None:
        cfg = _bare_config(
            concern=StorageBackend(kind="memory"),
            dcn=StorageBackend(kind="memory"),
            llm=LLMSettings(provider="azure"),
        )
        with pytest.raises(RuntimeError, match="deployment"):
            build_runtime(
                cfg,
                env={"AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com/"},
            )

    def test_azure_with_deployment_and_env(self) -> None:
        cfg = _bare_config(
            concern=StorageBackend(kind="memory"),
            dcn=StorageBackend(kind="memory"),
            llm=LLMSettings(provider="azure"),
        )
        with build_runtime(
            cfg,
            env={
                "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com/",
                "AZURE_OPENAI_API_KEY": "azkey-fake",
                "AZURE_OPENAI_DEPLOYMENT": "my-deployment",
            },
        ) as built:
            assert built.llm_label == "azure/my-deployment"

    def test_openai_honours_config_overrides(self) -> None:
        cfg = _bare_config(
            concern=StorageBackend(kind="memory"),
            dcn=StorageBackend(kind="memory"),
            llm=LLMSettings.model_validate(
                {
                    "provider": "openai",
                    "timeout_seconds": 5.0,
                    "model": "gpt-9000-imaginary",
                    "api_key": "sk-from-config",
                }
            ),
        )
        with build_runtime(cfg, env={}) as built:
            assert built.llm_label == "openai/gpt-9000-imaginary"


class TestExplicitEnvIsHermetic:
    """Codex P1 on PR-17: explicit ``env=`` must not leak to ``os.environ``."""

    def test_openai_without_key_in_explicit_env_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-real-from-os-environ")
        cfg = _bare_config(
            concern=StorageBackend(kind="memory"),
            dcn=StorageBackend(kind="memory"),
            llm=LLMSettings(provider="openai"),
        )
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
            build_runtime(cfg, env={})

    def test_anthropic_without_key_in_explicit_env_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-real")
        cfg = _bare_config(
            concern=StorageBackend(kind="memory"),
            dcn=StorageBackend(kind="memory"),
            llm=LLMSettings(provider="anthropic"),
        )
        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
            build_runtime(cfg, env={})

    def test_azure_without_credentials_in_explicit_env_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Both endpoint and api_key live in os.environ; the explicit
        # env mapping only carries the deployment — every other
        # credential must come from the injected env, not os.environ.
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://leak.openai.azure.com/")
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "leaked-key")
        cfg = _bare_config(
            concern=StorageBackend(kind="memory"),
            dcn=StorageBackend(kind="memory"),
            llm=LLMSettings(provider="azure"),
        )
        with pytest.raises(RuntimeError, match=r"AZURE_OPENAI_(ENDPOINT|API_KEY)"):
            build_runtime(cfg, env={"AZURE_OPENAI_DEPLOYMENT": "my-deployment"})


class TestAzureExtras:
    """Codex P2 on PR-17: Azure must honour timeout + OPENAI_API_VERSION env."""

    @staticmethod
    def _patch_azure(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
        """Replace the lazy Azure client with a kwargs-capturing stub."""
        import opencoat_runtime_llm as llm_pkg

        captured: dict[str, object] = {}

        def fake_client(**kwargs: object) -> object:
            captured.update(kwargs)
            return object()

        monkeypatch.setattr(llm_pkg, "AzureOpenAILLMClient", fake_client, raising=False)
        return captured

    def test_azure_picks_api_version_from_openai_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured = self._patch_azure(monkeypatch)
        cfg = _bare_config(
            concern=StorageBackend(kind="memory"),
            dcn=StorageBackend(kind="memory"),
            llm=LLMSettings(provider="azure"),
        )
        build_runtime(
            cfg,
            env={
                "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com/",
                "AZURE_OPENAI_API_KEY": "azkey-fake",
                "AZURE_OPENAI_DEPLOYMENT": "my-deployment",
                "OPENAI_API_VERSION": "2099-12-31",
            },
        )
        assert captured["api_version"] == "2099-12-31"

    def test_azure_propagates_timeout_seconds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured = self._patch_azure(monkeypatch)
        cfg = _bare_config(
            concern=StorageBackend(kind="memory"),
            dcn=StorageBackend(kind="memory"),
            llm=LLMSettings(provider="azure", timeout_seconds=42.5),
        )
        build_runtime(
            cfg,
            env={
                "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com/",
                "AZURE_OPENAI_API_KEY": "azkey-fake",
                "AZURE_OPENAI_DEPLOYMENT": "my-deployment",
            },
        )
        assert captured["timeout_seconds"] == 42.5
