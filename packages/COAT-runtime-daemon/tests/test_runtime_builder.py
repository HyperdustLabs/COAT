"""Tests for ``COAT_runtime_daemon.build_runtime`` (M4 PR-17)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from COAT_runtime_core import COATRuntime
from COAT_runtime_core.llm import StubLLMClient
from COAT_runtime_daemon import build_runtime
from COAT_runtime_daemon.config.loader import (
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
from COAT_runtime_protocol import (
    Advice,
    AdviceType,
    Concern,
    JoinpointEvent,
    Pointcut,
    WeavingLevel,
    WeavingOperation,
    WeavingPolicy,
)
from COAT_runtime_protocol.envelopes import PointcutMatch
from COAT_runtime_storage.memory import MemoryConcernStore, MemoryDCNStore
from COAT_runtime_storage.sqlite import SqliteConcernStore, SqliteDCNStore


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
            assert isinstance(built.runtime, COATRuntime)
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
