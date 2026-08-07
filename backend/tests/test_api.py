import os
import json
import sqlite3
import tempfile
import time
import tomllib
import zipfile
from datetime import date
from io import BytesIO
from pathlib import Path
from threading import Event

import pytest

test_data_root = Path(__file__).resolve().parents[2] / ".tmp" / "tests"
test_data_root.mkdir(parents=True, exist_ok=True)
os.environ["STOCKLLM_DATA_DIR"] = tempfile.mkdtemp(prefix="stockllm-api-", dir=test_data_root)
os.environ["STOCKLLM_ENABLE_DEMO"] = "1"

from fastapi.testclient import TestClient

from stockllm import __version__
from stockllm.ai import ModelGateway
from stockllm.chat_service import (
    ChatNotFoundError,
    ChatService,
    MAX_CHAT_CONTEXT_CHARS,
    MAX_CHAT_HISTORY_MESSAGE_CHARS,
    ResearchRunNotFoundError,
    SKILLS,
)
from stockllm.main import app, create_app, create_application_services, db, service
from stockllm.market_service import MarketDataUnavailableError, MarketService
from stockllm.model_settings_service import ModelConfigurationError, ModelConnectionError, ModelSettingsService
from stockllm.db import Database
from stockllm.models import (
    ChatCreate,
    ChatMessageCreate,
    ChatSession,
    Candidate,
    HealthResponse,
    ModelConfigInput,
    ProviderCheck,
    SelectionRun,
    SelectionRunCreate,
    SourceMeta,
    StockResearch,
    WatchlistItem,
)
from stockllm.providers import AKShareProvider, DemoProvider, ProviderUnavailable, ResearchProvider
from stockllm.providers.status import probe_source_statuses
from stockllm.repositories import (
    ChatRepository,
    DiagnosticsRepository,
    DuplicateWatchlistItemError,
    ResearchRunRepository,
    SettingsRepository,
    WatchlistRepository,
)
from stockllm.service import (
    ResearchQueueFullError,
    ResearchService,
    SKILLS as LEGACY_SKILLS,
    SelectionRunInProgressError,
    SelectionRunNotFoundError,
)
from stockllm.system_service import SystemService
from stockllm.tasks import ResearchTaskRunner
from stockllm.watchlist_service import WatchlistDataUnavailableError, WatchlistService


client = TestClient(app)


@pytest.fixture(autouse=True)
def isolate_model_credentials(monkeypatch):
    monkeypatch.setattr(service.gateway, "get_key", lambda: None)


def wait_for_run(run_id: str) -> dict:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/selection-runs/{run_id}")
        payload = response.json()
        if payload["status"] in {"complete", "failed"}:
            return payload
        time.sleep(0.01)
    raise AssertionError(f"Research run {run_id} did not finish")


def test_openapi_preserves_modular_route_contracts() -> None:
    schema = client.get("/openapi.json").json()
    assert schema["paths"]["/api/v1/health"]["get"]["tags"] == ["system"]
    assert schema["paths"]["/api/v1/stocks/search"]["get"]["tags"] == ["market"]
    assert schema["paths"]["/api/v1/watchlist"]["get"]["tags"] == ["watchlist"]
    assert schema["paths"]["/api/v1/models/config"]["get"]["tags"] == ["models"]
    assert schema["paths"]["/api/v1/system/diagnostics"]["get"]["tags"] == ["system"]
    assert schema["paths"]["/api/v1/selection-runs"]["post"]["tags"] == ["research"]
    assert schema["paths"]["/api/v1/chats"]["post"]["tags"] == ["chats"]

    def response_schema(path: str, method: str = "get") -> dict:
        return schema["paths"][path][method]["responses"]["200"]["content"]["application/json"]["schema"]

    assert response_schema("/api/v1/strategies")["items"]["$ref"].endswith("/StrategyDefinition")
    assert response_schema("/api/v1/stocks/search")["items"]["$ref"].endswith("/StockSearchResult")
    assert response_schema("/api/v1/stocks/{code}/research")["$ref"].endswith("/StockResearch")
    assert response_schema("/api/v1/providers/status")["items"]["$ref"].endswith("/ProviderCheck")
    assert response_schema("/api/v1/providers/status/check", "post")["items"]["$ref"].endswith("/ProviderCheck")
    assert response_schema("/api/v1/health")["$ref"].endswith("/HealthResponse")
    assert response_schema("/api/v1/watchlist/batch-delete", "post")["$ref"].endswith("/BatchDeleteResponse")
    assert response_schema("/api/v1/watchlist/{code}", "delete")["$ref"].endswith("/DeleteResponse")
    assert response_schema("/api/v1/models/test", "post")["$ref"].endswith("/ModelTestResponse")
    assert response_schema("/api/v1/selection-runs/batch-delete", "post")["$ref"].endswith("/BatchDeleteResponse")
    assert response_schema("/api/v1/selection-runs/{run_id}", "delete")["$ref"].endswith("/DeleteResponse")
    assert response_schema("/api/v1/chats/batch-delete", "post")["$ref"].endswith("/BatchDeleteResponse")
    assert response_schema("/api/v1/skills")["items"]["$ref"].endswith("/SkillDefinition")
    assert response_schema("/api/v1/system/storage")["$ref"].endswith("/StorageStatistics")
    assert response_schema("/api/v1/system/storage/clear", "post")["$ref"].endswith("/StorageStatistics")
    assert response_schema("/api/v1/system/diagnostics")["$ref"].endswith("/SystemDiagnostics")
    assert response_schema("/api/v1/system/logs")["items"]["$ref"].endswith("/LogEntry")
    assert response_schema("/api/v1/system/log-level", "post")["$ref"].endswith("/LogLevelView")


def test_main_module_only_owns_api_assembly_and_health() -> None:
    def expanded_routes(routes):
        for route in routes:
            original_router = getattr(route, "original_router", None)
            if original_router is not None:
                yield from expanded_routes(original_router.routes)
            else:
                yield route

    business_routes = [
        route
        for route in expanded_routes(app.routes)
        if getattr(route, "path", "").startswith("/api/v1/")
        and route.path != "/api/v1/health"
    ]

    assert business_routes
    assert all(route.endpoint.__module__.startswith("stockllm.routers.") for route in business_routes)


def test_application_factory_uses_one_explicit_dependency_graph(tmp_path) -> None:
    dependencies = create_application_services(Database(tmp_path / "stockllm.db"))
    isolated_app = create_app(dependencies)

    assert isolated_app.state.services is dependencies
    assert dependencies.market.db is dependencies.db
    assert dependencies.watchlist.db is dependencies.db
    assert dependencies.research.db is dependencies.db
    assert dependencies.chat.db is dependencies.db
    assert dependencies.model_settings.db is dependencies.db
    assert dependencies.system.db is dependencies.db
    assert dependencies.research.gateway is dependencies.gateway
    assert dependencies.chat.gateway is dependencies.gateway
    assert dependencies.chat.market is dependencies.market
    assert dependencies.model_settings.gateway is dependencies.gateway
    assert dependencies.research.chat_service is dependencies.chat
    dependencies.runner.shutdown()


def test_project_versions_stay_in_sync() -> None:
    project_root = Path(__file__).resolve().parents[2]
    python_version = tomllib.loads(
        (project_root / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]["version"]
    frontend_version = json.loads(
        (project_root / "frontend" / "package.json").read_text(encoding="utf-8")
    )["version"]
    tauri_version = json.loads(
        (project_root / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8")
    )["version"]
    cargo = tomllib.loads(
        (project_root / "src-tauri" / "Cargo.toml").read_text(encoding="utf-8")
    )

    assert {python_version, frontend_version, tauri_version, cargo["package"]["version"]} == {
        __version__
    }


def test_provider_package_keeps_contract_demo_and_live_implementations_separate() -> None:
    assert ResearchProvider.__module__ == "stockllm.providers.base"
    assert ProviderUnavailable.__module__ == "stockllm.providers.base"
    assert DemoProvider.__module__ == "stockllm.providers.demo"
    assert AKShareProvider.__module__ == "stockllm.providers.live"


def test_model_package_keeps_domain_contracts_separate() -> None:
    assert SourceMeta.__module__ == "stockllm.models.common"
    assert ProviderCheck.__module__ == "stockllm.models.market"
    assert StockResearch.__module__ == "stockllm.models.market"
    assert SelectionRunCreate.__module__ == "stockllm.models.research"
    assert SelectionRun.__module__ == "stockllm.models.research"
    assert HealthResponse.__module__ == "stockllm.models.system"
    assert WatchlistItem.__module__ == "stockllm.models.watchlist"
    assert ChatSession.__module__ == "stockllm.models.chat"


def test_chat_service_owns_chat_contract_and_research_service_uses_a_compatibility_proxy() -> None:
    assert ChatService.__module__ == "stockllm.chat_service"
    assert not issubclass(ResearchService, ChatService)
    assert SKILLS
    assert SKILLS is LEGACY_SKILLS
    assert [skill.id for skill in ChatService(db).list_skills()] == list(SKILLS)
    assert "create_chat" in ResearchService.__dict__
    assert "get_events_after" in ResearchService.__dict__
    source = (Path(__file__).resolve().parents[1] / "stockllm" / "chat_service.py").read_text(
        encoding="utf-8"
    )
    assert "from .providers" not in source


def test_chat_service_validates_linked_research_run_and_router_maps_not_found() -> None:
    with pytest.raises(ResearchRunNotFoundError):
        ChatService(db).create_chat(ChatCreate(run_id="missing-run"))

    response = client.post("/api/v1/chats", json={"run_id": "missing-run"})

    assert response.status_code == 404
    assert response.json()["detail"] == "关联的选股任务不存在"

    with pytest.raises(ChatNotFoundError):
        service.chat_service.add_message(
            "missing-chat",
            ChatMessageCreate(content="测试不存在的对话", skill="verify_sources"),
        )

    missing_message = client.post(
        "/api/v1/chats/missing-chat/messages",
        json={"content": "测试不存在的对话", "skill": "verify_sources"},
    )
    assert missing_message.status_code == 404
    assert missing_message.json()["detail"] == "对话不存在"


def test_market_service_owns_provider_workflow() -> None:
    assert MarketService.__module__ == "stockllm.market_service"


def test_watchlist_service_owns_watchlist_workflow() -> None:
    assert WatchlistService.__module__ == "stockllm.watchlist_service"


def test_model_settings_service_owns_model_configuration() -> None:
    assert ModelSettingsService.__module__ == "stockllm.model_settings_service"


def test_system_service_owns_storage_logging_and_diagnostics_workflows() -> None:
    assert SystemService.__module__ == "stockllm.system_service"


def test_router_modules_do_not_import_provider_or_engine_implementations() -> None:
    router_root = Path(__file__).resolve().parents[1] / "stockllm" / "routers"
    assert "from ..providers" not in (router_root / "market.py").read_text(encoding="utf-8")
    assert "from ..providers" not in (router_root / "watchlist.py").read_text(encoding="utf-8")
    assert "from ..engine" not in (router_root / "research.py").read_text(encoding="utf-8")
    assert "SKILLS" not in (router_root / "chats.py").read_text(encoding="utf-8")


def test_cache_adapters_depend_on_storage_not_diagnostics() -> None:
    package_root = Path(__file__).resolve().parents[1] / "stockllm"
    for path in [
        package_root / "link_reader.py",
        package_root / "providers" / "content.py",
        package_root / "providers" / "live.py",
    ]:
        source = path.read_text(encoding="utf-8")
        assert "diagnostics import cache_write_lock" not in source
        assert "storage import" in source
        assert "atomic_cache_write" in source


def test_research_service_owns_queue_and_deletion_rules(tmp_path) -> None:
    isolated_service = ResearchService(Database(tmp_path / "stockllm.db"))
    request = SelectionRunCreate(data_mode="demo")

    with pytest.raises(ResearchQueueFullError):
        isolated_service.enqueue_run(request, lambda _run_id, _request: False)
    failed_runs = isolated_service.list_runs()
    assert failed_runs[0]["status"] == "failed"

    run = isolated_service.start_run(request)
    with pytest.raises(SelectionRunInProgressError):
        isolated_service.delete_run_checked(run.id)
    with pytest.raises(SelectionRunNotFoundError):
        isolated_service.require_run("missing-run")


def test_application_services_translate_provider_failures_at_service_boundary(monkeypatch, tmp_path) -> None:
    class FailingProvider:
        @staticmethod
        def search(_query: str):
            raise ProviderUnavailable("provider unavailable")

    monkeypatch.setattr("stockllm.market_service.get_provider", lambda _mode: FailingProvider())
    with pytest.raises(MarketDataUnavailableError):
        MarketService(Database(tmp_path / "market.db")).search("600519", "live")

    monkeypatch.setattr("stockllm.watchlist_service.get_provider", lambda _mode: FailingProvider())
    with pytest.raises(WatchlistDataUnavailableError):
        WatchlistService(Database(tmp_path / "watchlist.db")).add_item("600519", "", "live")


def test_application_services_translate_unexpected_provider_failures(monkeypatch, tmp_path) -> None:
    class ExplodingProvider:
        @staticmethod
        def search(_query: str):
            raise RuntimeError("adapter exploded")

    monkeypatch.setattr("stockllm.market_service.get_provider", lambda _mode: ExplodingProvider())
    with pytest.raises(MarketDataUnavailableError, match="adapter exploded"):
        MarketService(Database(tmp_path / "market-runtime.db")).search("600519", "live")

    monkeypatch.setattr("stockllm.watchlist_service.get_provider", lambda _mode: ExplodingProvider())
    with pytest.raises(WatchlistDataUnavailableError, match="adapter exploded"):
        WatchlistService(Database(tmp_path / "watchlist-runtime.db")).add_item("600519", "", "live")

    monkeypatch.setattr(
        "stockllm.market_service.get_provider",
        lambda _mode: (_ for _ in ()).throw(RuntimeError("status probe exploded")),
    )
    statuses = MarketService(Database(tmp_path / "provider-status-runtime.db")).check_provider_status()
    assert statuses and all(item["status"] == "unavailable" for item in statuses)

    monkeypatch.setattr("stockllm.market_service.get_provider", lambda _mode: object())
    statuses = MarketService(Database(tmp_path / "provider-status-contract.db")).check_provider_status()
    assert statuses and all(item["status"] == "unavailable" for item in statuses)


def test_model_service_exposes_typed_configuration_and_connection_errors(monkeypatch, tmp_path) -> None:
    database = Database(tmp_path / "model-errors.db")
    gateway = ModelGateway(database)
    settings = ModelSettingsService(database, gateway)
    monkeypatch.setattr(gateway, "set_key", lambda _key: (_ for _ in ()).throw(RuntimeError("keyring failed")))
    with pytest.raises(ModelConfigurationError, match="keyring failed"):
        settings.save_config(ModelConfigInput(
            base_url="https://api.deepseek.com",
            model="test-model",
            api_key="valid-key",
        ))

    monkeypatch.setattr(gateway, "test", lambda: (_ for _ in ()).throw(RuntimeError("endpoint failed")))
    with pytest.raises(ModelConnectionError, match="endpoint failed"):
        settings.test_connection()


def test_database_facade_composes_separate_domain_repositories() -> None:
    assert issubclass(Database, WatchlistRepository)
    assert issubclass(Database, SettingsRepository)
    assert issubclass(Database, ChatRepository)
    assert issubclass(Database, ResearchRunRepository)
    assert issubclass(Database, DiagnosticsRepository)
    assert "list_watchlist" in WatchlistRepository.__dict__
    assert "get_setting" in SettingsRepository.__dict__
    assert "list_chats" in ChatRepository.__dict__
    assert "get_events_after" in ResearchRunRepository.__dict__
    assert "save_run_and_append_event" in ResearchRunRepository.__dict__
    assert "diagnostic_business_data" in DiagnosticsRepository.__dict__


def test_market_data_mode_is_validated_before_provider_lookup() -> None:
    assert client.get("/api/v1/stocks/search?q=600519&data_mode=invalid").status_code == 422
    assert client.get("/api/v1/stocks/600519/research?data_mode=invalid").status_code == 422


def test_demo_stock_research_matches_public_response_model() -> None:
    payload = DemoProvider().research("600519", date(2026, 8, 1))

    research = StockResearch.model_validate(payload)

    assert research.code == "600519"
    assert research.source.status == "demo"
    assert research.history


def test_provider_fallback_matches_public_response_model(monkeypatch) -> None:
    def unavailable(_: str):
        raise ProviderUnavailable("测试数据源不可用")

    monkeypatch.setattr("stockllm.market_service.get_provider", unavailable)

    response = client.post("/api/v1/providers/status/check")

    assert response.status_code == 200
    checks = [ProviderCheck.model_validate(item) for item in response.json()]
    assert len(checks) == 6
    assert all(item.status == "unavailable" for item in checks)


def test_akshare_calls_retry_once_after_transient_failure(monkeypatch) -> None:
    class OptionContext:
        def __enter__(self):
            return None

        def __exit__(self, *_):
            return None

    class PandasStub:
        @staticmethod
        def option_context(*_):
            return OptionContext()

    provider = object.__new__(AKShareProvider)
    provider.pd = PandasStub()
    attempts = 0

    def fetch():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError(22, "Invalid argument")
        return "recovered"

    monkeypatch.setattr("stockllm.providers.live.time.sleep", lambda _: None)

    assert provider._akshare_frame(fetch) == "recovered"
    assert attempts == 2


def test_provider_source_probe_preserves_all_adapter_failures(tmp_path) -> None:
    class FailingAKShare:
        @staticmethod
        def stock_news_em(**_):
            raise RuntimeError("news unavailable")

        @staticmethod
        def stock_zh_a_disclosure_report_cninfo(**_):
            raise RuntimeError("notices unavailable")

    class FailingContext:
        def __enter__(self):
            raise RuntimeError("baostock unavailable")

        def __exit__(self, *_):
            return None

    class StubContext:
        ak = FailingAKShare()
        cache_dir = tmp_path

        @staticmethod
        def _spot_frame(force_refresh: bool = False):
            assert force_refresh
            raise RuntimeError("spot unavailable")

        @staticmethod
        def _akshare_frame(fetch):
            return fetch()

        @staticmethod
        def _baostock():
            return FailingContext()

        @staticmethod
        def _query_rows(_):
            return []

    statuses = probe_source_statuses(StubContext())

    assert len(statuses) == 6
    assert all(item["status"] == "unavailable" for item in statuses)
    assert {item["provider"] for item in statuses} == {"AKShare", "BaoStock"}


def test_ai_selection_skips_keyring_when_model_is_disconnected(monkeypatch) -> None:
    gateway = ModelGateway(db)
    key_reads = 0

    def missing_key() -> None:
        nonlocal key_reads
        key_reads += 1
        return None

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    db.set_setting("model.connection_status", "disconnected")
    monkeypatch.setattr(gateway, "get_key", missing_key)
    monkeypatch.setattr(gateway, "_chat", lambda *_args, **_kwargs: pytest.fail("should not call model"))
    candidate = Candidate(
        code="600519",
        name="贵州茅台",
        sector="消费",
        price=1500,
        change_pct=0,
        checks=[],
        evidence=[],
        passed=0,
        concerns=0,
        completeness=1,
    )

    result = gateway.select([candidate], SelectionRunCreate(data_mode="demo"))

    assert result.status == "unavailable"
    assert key_reads == 0


def test_model_gateway_exposes_public_fallback_selection_contract() -> None:
    fallback = ModelGateway.fallback_selection([], "测试回退")

    assert fallback.status == "unavailable"
    assert fallback.data_gaps == ["测试回退"]
    assert ModelGateway._fallback([], "兼容回退").data_gaps == ["兼容回退"]


def test_database_schema_version_and_incomplete_run_resume() -> None:
    with tempfile.TemporaryDirectory(prefix="stockllm-db-", dir=test_data_root) as isolated_root:
        isolated_db = Database(Path(isolated_root) / "stockllm.db")
        with isolated_db.connect() as connection:
            version = connection.execute(
                "SELECT value FROM schema_meta WHERE key='version'"
            ).fetchone()["value"]
        assert version == str(Database.SCHEMA_VERSION)

        isolated_service = ResearchService(isolated_db)
        run = isolated_service.start_run(SelectionRunCreate(
            risk_profile="balanced",
            horizon="medium",
            strategy="trend",
            as_of="2026-08-01",
            data_mode="demo",
        ))
        pending = isolated_service.prepare_incomplete_runs()
        assert [(run_id, request.data_mode) for run_id, request in pending] == [(run.id, "demo")]
        recovered = isolated_db.get_run(run.id)
        assert recovered["status"] == "pending"
        assert recovered["error"] is None


def test_database_connection_enables_foreign_keys_and_rejects_future_schema() -> None:
    with tempfile.TemporaryDirectory(prefix="stockllm-schema-", dir=test_data_root) as isolated_root:
        database_path = Path(isolated_root) / "stockllm.db"
        isolated_db = Database(database_path)
        with isolated_db.connect() as connection:
            assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
            connection.execute(
                "UPDATE schema_meta SET value=? WHERE key='version'",
                (str(Database.SCHEMA_VERSION + 1),),
            )

        with pytest.raises(RuntimeError, match="newer than supported"):
            Database(database_path)


def test_database_connection_has_bounded_writer_wait_timeout(tmp_path) -> None:
    isolated_db = Database(tmp_path / "stockllm.db")

    with isolated_db.connect() as connection:
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 10_000


def test_run_snapshot_and_event_are_rolled_back_together(tmp_path) -> None:
    isolated_db = Database(tmp_path / "stockllm.db")
    isolated_service = ResearchService(isolated_db)
    run = isolated_service.start_run(SelectionRunCreate(data_mode="demo"))
    original = isolated_db.get_run(run.id)
    assert original is not None

    with isolated_db.connect() as connection:
        connection.execute(
            "CREATE TRIGGER reject_terminal_event BEFORE INSERT ON run_events "
            "WHEN NEW.event_type='terminal' "
            "BEGIN SELECT RAISE(ABORT, 'terminal event rejected'); END"
        )

    terminal = {**original, "status": "complete"}
    with pytest.raises(sqlite3.IntegrityError, match="terminal event rejected"):
        isolated_db.save_run_and_append_event(
            run.id,
            original["created_at"],
            terminal,
            "terminal",
            {"stage": "complete"},
        )

    assert isolated_db.get_run(run.id)["status"] == "pending"
    assert [event["type"] for event in isolated_db.get_events(run.id)] == ["stage"]


def test_research_task_runner_bounds_pending_work(monkeypatch) -> None:
    release = Event()

    class BlockingService:
        @staticmethod
        def execute_run(run_id, request) -> None:
            release.wait(timeout=2)

    monkeypatch.setenv("STOCKLLM_RESEARCH_WORKERS", "1")
    monkeypatch.setenv("STOCKLLM_RESEARCH_QUEUE", "1")
    task_runner = ResearchTaskRunner(BlockingService())
    request = SelectionRunCreate(data_mode="demo")
    assert task_runner.submit("first", request)
    assert task_runner.submit("second", request)
    assert not task_runner.submit("overflow", request)
    release.set()
    task_runner.shutdown()


def test_research_task_runner_records_unexpected_failures(monkeypatch) -> None:
    failed = Event()
    captured: list[tuple[str, str]] = []

    class FailingService:
        @staticmethod
        def execute_run(run_id, request) -> None:
            raise RuntimeError("worker crashed")

        @staticmethod
        def fail_run(run_id: str, message: str) -> None:
            captured.append((run_id, message))
            failed.set()

    monkeypatch.setenv("STOCKLLM_RESEARCH_WORKERS", "1")
    task_runner = ResearchTaskRunner(FailingService())
    assert task_runner.submit("failed-run", SelectionRunCreate(data_mode="demo"))
    assert failed.wait(timeout=2)
    assert captured == [("failed-run", "研究任务意外失败：worker crashed")]
    task_runner.shutdown()


def test_provider_status_uses_provider_and_child_item_fields(monkeypatch) -> None:
    class StubProvider:
        @staticmethod
        def source_statuses() -> list[dict]:
            return [{
                "id": "akshare-sina-spot",
                "provider": "AKShare",
                "name": "新浪财经 A 股行情",
                "description": "全市场最新价格、涨跌幅与成交额",
                "status": "available",
                "message": "探测成功",
                "checked_at": "2026-08-04T00:00:00+00:00",
            }]

    monkeypatch.setattr("stockllm.market_service.get_provider", lambda _: StubProvider())
    response = client.post("/api/v1/providers/status/check")
    assert response.status_code == 200
    item = response.json()[0]
    assert item["provider"] == "AKShare"
    assert item["name"] == "新浪财经 A 股行情"
    assert "adapter" not in item
    assert "content" not in item

    monkeypatch.setattr(
        "stockllm.market_service.get_provider",
        lambda _: (_ for _ in ()).throw(RuntimeError("不应探测")),
    )
    cached = client.get("/api/v1/providers/status")
    assert cached.status_code == 200
    assert cached.json() == response.json()


def test_model_connection_status_is_cached_without_automatic_checks(monkeypatch) -> None:
    monkeypatch.setattr(service.gateway, "get_key", lambda: "configured-key")
    db.set_setting("model.connection_status", "disconnected")
    assert client.get("/api/v1/models/config").json()["connection_status"] == "disconnected"

    monkeypatch.setattr(service.gateway, "test", lambda: "连接成功")
    assert client.post("/api/v1/models/test").status_code == 200
    assert client.get("/api/v1/models/config").json()["connection_status"] == "connected"

    def fail_test() -> str:
        raise RuntimeError("测试失败")

    monkeypatch.setattr(service.gateway, "test", fail_test)
    assert client.post("/api/v1/models/test").status_code == 503
    assert client.get("/api/v1/models/config").json()["connection_status"] == "disconnected"


def test_model_connection_status_is_disconnected_without_key(monkeypatch) -> None:
    monkeypatch.setattr(service.gateway, "get_key", lambda: None)
    db.set_setting("model.connection_status", "connected")

    response = client.get("/api/v1/models/config")

    assert response.status_code == 200
    assert response.json()["key_configured"] is False
    assert response.json()["connection_status"] == "disconnected"
    assert db.get_setting("model.connection_status", "disconnected") == "disconnected"


def test_selection_workflow_without_model_key() -> None:
    response = client.post(
        "/api/v1/selection-runs",
        json={
            "risk_profile": "balanced", "horizon": "medium", "strategy": "trend",
            "as_of": "2026-08-01", "data_mode": "demo",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "pending"
    assert payload["provider"]["status"] == "pending"
    payload = wait_for_run(payload["id"])
    assert payload["status"] == "complete"
    assert payload["provider"]["status"] == "demo"
    assert len(payload["candidates"]) > 0
    assert set(choice["code"] for choice in payload["ai_selection"]["top_three"]).issubset(
        set(candidate["code"] for candidate in payload["candidates"])
    )


def test_live_failure_is_explicit() -> None:
    response = client.post(
        "/api/v1/selection-runs",
        json={
            "risk_profile": "balanced", "horizon": "medium", "strategy": "trend",
            "as_of": "2026-08-01", "data_mode": "live",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "pending"
    payload = wait_for_run(payload["id"])
    assert payload["status"] == "failed"
    assert payload["candidates"] == []


def test_selection_events_follow_stage_order() -> None:
    response = client.post(
        "/api/v1/selection-runs",
        json={
            "risk_profile": "balanced", "horizon": "medium", "strategy": "trend",
            "as_of": "2026-08-01", "data_mode": "demo",
        },
    )
    run_id = response.json()["id"]
    events = client.get(f"/api/v1/selection-runs/{run_id}/events").text
    positions = [events.index(f'"stage": "{stage}"') for stage in ("queued", "preparing", "filtering", "comparing", "complete")]
    assert positions == sorted(positions)


def test_selection_event_stream_resumes_after_last_event_id() -> None:
    run = client.post(
        "/api/v1/selection-runs",
        json={
            "risk_profile": "balanced", "horizon": "medium", "strategy": "trend",
            "as_of": "2026-08-01", "data_mode": "demo",
        },
    ).json()
    response = client.get(
        f"/api/v1/selection-runs/{run['id']}/events",
        headers={"Last-Event-ID": "0"},
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    assert "id: 0\n" not in response.text
    assert "id: 1\n" in response.text
    assert "event: end" in response.text


def test_delete_selection_run_removes_related_records() -> None:
    response = client.post(
        "/api/v1/selection-runs",
        json={
            "risk_profile": "balanced", "horizon": "medium", "strategy": "trend",
            "as_of": "2026-08-01", "data_mode": "demo",
        },
    )
    run_id = response.json()["id"]
    wait_for_run(run_id)
    chat = client.post("/api/v1/chats", json={"run_id": run_id}).json()
    with db.connect() as connection:
        connection.execute(
            "INSERT INTO chat_messages(id, chat_id, role, content, created_at, tool_traces) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("delete-test-message", chat["id"], "user", "测试", "2026-08-01T00:00:00+00:00", "[]"),
        )

    assert client.delete(f"/api/v1/selection-runs/{run_id}").status_code == 200
    assert client.get(f"/api/v1/selection-runs/{run_id}").status_code == 404
    assert client.delete(f"/api/v1/selection-runs/{run_id}").status_code == 404
    with db.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM run_events WHERE run_id=?", (run_id,)
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM chats WHERE run_id=?", (run_id,)
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM chat_messages WHERE id=?", ("delete-test-message",)
        ).fetchone()[0] == 0


def test_batch_delete_selection_runs_is_all_or_nothing() -> None:
    run_ids = []
    for strategy in ("trend", "quality"):
        response = client.post(
            "/api/v1/selection-runs",
            json={
                "risk_profile": "balanced", "horizon": "medium", "strategy": strategy,
                "as_of": "2026-08-01", "data_mode": "demo",
            },
        )
        run_ids.append(response.json()["id"])
    for run_id in run_ids:
        wait_for_run(run_id)

    rejected = client.post(
        "/api/v1/selection-runs/batch-delete",
        json={"ids": [run_ids[0], "missing-run"]},
    )
    assert rejected.status_code == 404
    assert client.get(f"/api/v1/selection-runs/{run_ids[0]}").status_code == 200

    deleted = client.post("/api/v1/selection-runs/batch-delete", json={"ids": run_ids})
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] == 2
    assert all(client.get(f"/api/v1/selection-runs/{run_id}").status_code == 404 for run_id in run_ids)


def test_watchlist_crud_uses_sqlite_as_source_of_truth() -> None:
    client.delete("/api/v1/watchlist/600519")
    response = client.post(
        "/api/v1/watchlist",
        json={"code": "600519", "note": "关注经营变化", "data_mode": "demo"},
    )
    assert response.status_code == 201
    created = response.json()
    assert created["code"] == "600519"
    assert created["name"] == "贵州茅台"

    listed = client.get("/api/v1/watchlist").json()
    assert any(item["code"] == "600519" for item in listed)

    updated = client.put("/api/v1/watchlist/600519", json={"note": "等待下一期财报"})
    assert updated.status_code == 200
    assert updated.json()["note"] == "等待下一期财报"

    duplicate = client.post(
        "/api/v1/watchlist",
        json={"code": "600519", "data_mode": "demo"},
    )
    assert duplicate.status_code == 409

    assert client.delete("/api/v1/watchlist/600519").status_code == 200
    assert all(item["code"] != "600519" for item in client.get("/api/v1/watchlist").json())


def test_watchlist_repository_translates_duplicate_constraint() -> None:
    client.delete("/api/v1/watchlist/600519")
    db.add_watchlist_item("600519", "贵州茅台", "")

    with pytest.raises(DuplicateWatchlistItemError):
        db.add_watchlist_item("600519", "贵州茅台", "")

    client.delete("/api/v1/watchlist/600519")


def test_watchlist_legacy_import_is_idempotent() -> None:
    client.delete("/api/v1/watchlist/600036")
    payload = [{"code": "600036", "name": "招商银行", "note": "旧版备注"}]
    first = client.post("/api/v1/watchlist/import", json=payload)
    second = client.post("/api/v1/watchlist/import", json=payload)
    assert first.status_code == 200
    assert second.status_code == 200
    assert sum(item["code"] == "600036" for item in second.json()) == 1
    client.delete("/api/v1/watchlist/600036")


def test_batch_delete_watchlist_is_all_or_nothing() -> None:
    payload = [
        {"code": "600036", "name": "招商银行", "note": ""},
        {"code": "600519", "name": "贵州茅台", "note": ""},
    ]
    client.post("/api/v1/watchlist/import", json=payload)

    rejected = client.post(
        "/api/v1/watchlist/batch-delete",
        json={"ids": ["600036", "000000"]},
    )
    assert rejected.status_code == 404
    assert any(item["code"] == "600036" for item in client.get("/api/v1/watchlist").json())

    deleted = client.post(
        "/api/v1/watchlist/batch-delete",
        json={"ids": ["600036", "600519"]},
    )
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] == 2


def test_stock_chat_uses_live_research_context_and_conversation_history(monkeypatch) -> None:
    class StubProvider:
        @staticmethod
        def research(code: str, as_of) -> dict:
            return {
                "code": code,
                "name": "药明康德",
                "price": 141.35,
                "price_as_of": "2026-08-04",
                "evidence_sources": {"price": "AKShare", "ma": "BaoStock"},
            }

    captured: list[dict] = []

    def answer(question: str, context: str, instruction: str, history: list[dict] | None = None) -> str:
        captured.append({"question": question, "context": context, "history": history or []})
        return "基于已提供证据的回答"

    monkeypatch.setattr("stockllm.market_service.get_provider", lambda mode: StubProvider())
    monkeypatch.setattr(service.gateway, "answer", answer)

    chat = client.post("/api/v1/chats", json={"stock_code": "603259"}).json()
    first = client.post(
        f"/api/v1/chats/{chat['id']}/messages",
        json={"content": "价格来自哪里？", "skill": "verify_sources"},
    )
    assert first.status_code == 200
    assert '"price": "AKShare"' in captured[0]["context"]
    assert captured[0]["history"] == []

    second = client.post(
        f"/api/v1/chats/{chat['id']}/messages",
        json={"content": "上一条结论的数据日期呢？", "skill": "verify_sources"},
    )
    assert second.status_code == 200
    assert [message["role"] for message in captured[1]["history"]] == ["user", "assistant"]


def test_news_chat_reads_registered_links_and_records_trace(monkeypatch) -> None:
    class StubProvider:
        @staticmethod
        def research(code: str, as_of) -> dict:
            return {
                "code": code,
                "news": [{
                    "kind": "新闻",
                    "url": "https://finance.eastmoney.com/a/example.html",
                    "title": "测试新闻",
                }],
            }

    captured: list[str] = []
    read_calls: list[str] = []

    def read(url: str) -> dict:
        read_calls.append(url)
        return {
            "source_url": url,
            "resolved_url": url,
            "title": "测试新闻",
            "text": "这是应用从原始链接读取的完整正文。",
            "document_type": "html",
            "truncated": False,
            "fetched_at": "2026-08-05T09:00:00+00:00",
            "from_cache": False,
        }

    monkeypatch.setattr("stockllm.market_service.get_provider", lambda mode: StubProvider())
    monkeypatch.setattr("stockllm.chat_service.read_external_url", read)
    monkeypatch.setattr(
        service.gateway,
        "answer",
        lambda question, context, instruction, history=None: captured.append(context) or "已分析",
    )

    chat = client.post("/api/v1/chats", json={"stock_code": "600519"}).json()
    response = client.post(
        f"/api/v1/chats/{chat['id']}/messages",
        json={"content": "分析这条新闻", "skill": "analyze_news"},
    )
    assert response.status_code == 200
    assert read_calls == ["https://finance.eastmoney.com/a/example.html"]
    assert "应用从原始链接读取的完整正文" in captured[0]
    assert "读取外部链接 1 条" in response.json()["messages"][-1]["tool_traces"]

    client.post(
        f"/api/v1/chats/{chat['id']}/messages",
        json={"content": "价格来源是什么？", "skill": "verify_sources"},
    )
    assert len(read_calls) == 1


def test_chat_context_has_structured_research_document_and_history_limits(monkeypatch) -> None:
    long_summary = "可核验摘要" * 4_000
    news = [
        {
            "kind": "新闻",
            "url": f"https://finance.eastmoney.com/a/news-{index}.html",
            "title": f"新闻 {index}",
            "summary": long_summary,
        }
        for index in range(12)
    ]
    news.extend([
        {
            "kind": "公告",
            "url": f"https://www.cninfo.com.cn/disclosure/detail?announcementId={index}&announcementTime=2026-08-01",
            "title": f"公告 {index}",
            "summary": long_summary,
        }
        for index in range(2)
    ])

    class StubProvider:
        @staticmethod
        def research(code: str, as_of) -> dict:
            return {
                "code": code,
                "name": "测试公司",
                "history": [{"sequence": index, "close": 100 + index} for index in range(100)],
                "news": news,
            }

    captures: list[dict] = []
    read_calls: list[str] = []

    def read(url: str) -> dict:
        read_calls.append(url)
        return {
            "source_url": url,
            "resolved_url": url,
            "title": "外部正文",
            "text": "外部正文内容" * 4_000,
            "document_type": "html",
            "truncated": False,
            "fetched_at": "2026-08-05T09:00:00+00:00",
            "from_cache": False,
        }

    def answer(question: str, context: str, instruction: str, history=None) -> str:
        captures.append({"context": context, "history": history or []})
        return "较长的模型回答" * 2_000 if len(captures) == 1 else "完成"

    monkeypatch.setattr("stockllm.market_service.get_provider", lambda mode: StubProvider())
    monkeypatch.setattr("stockllm.chat_service.read_external_url", read)
    monkeypatch.setattr(service.gateway, "answer", answer)

    chat = client.post("/api/v1/chats", json={"stock_code": "600519"}).json()
    first = client.post(
        f"/api/v1/chats/{chat['id']}/messages",
        json={"content": "分析资讯", "skill": "analyze_news"},
    )
    assert first.status_code == 200
    assert len(read_calls) == 5
    assert len(captures[0]["context"]) <= MAX_CHAT_CONTEXT_CHARS
    assert captures[0]["context"].count('"sequence":') == 30
    assert captures[0]["context"].count("[资讯摘要已截断]") == 10
    assert captures[0]["context"].count("[外部正文已由应用截断]") == 5

    second = client.post(
        f"/api/v1/chats/{chat['id']}/messages",
        json={"content": "继续检查来源", "skill": "verify_sources"},
    )
    assert second.status_code == 200
    assistant_history = captures[1]["history"][1]["content"]
    assert len(assistant_history) == MAX_CHAT_HISTORY_MESSAGE_CHARS
    assert assistant_history.endswith("[历史消息已截断]")


def test_latest_chat_is_loaded_by_exact_research_context() -> None:
    first_run = client.post(
        "/api/v1/selection-runs",
        json={
            "risk_profile": "balanced", "horizon": "medium", "strategy": "trend",
            "as_of": "2026-08-01", "data_mode": "demo",
        },
    ).json()
    second_run = client.post(
        "/api/v1/selection-runs",
        json={
            "risk_profile": "balanced", "horizon": "medium", "strategy": "quality",
            "as_of": "2026-08-01", "data_mode": "demo",
        },
    ).json()
    first_chat = client.post("/api/v1/chats", json={"run_id": first_run["id"]}).json()
    second_chat = client.post("/api/v1/chats", json={"run_id": second_run["id"]}).json()
    with db.connect() as connection:
        connection.execute(
            "INSERT INTO chat_messages(id, chat_id, role, content, created_at, tool_traces) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (f"history-message-{first_chat['id']}", first_chat["id"], "user", "历史问题", "2026-08-01T00:00:00+00:00", "[]"),
        )

    loaded = client.get(f"/api/v1/chats/latest?run_id={first_run['id']}")
    assert loaded.status_code == 200
    assert loaded.json()["id"] == first_chat["id"]
    assert loaded.json()["messages"][0]["content"] == "历史问题"
    assert client.get(f"/api/v1/chats/latest?run_id={second_run['id']}").json()["id"] == second_chat["id"]
    assert client.get("/api/v1/chats/latest?stock_code=000001").json() is None
    assert client.get("/api/v1/chats/latest").status_code == 422


def test_chat_history_lists_summaries_and_supports_deletion() -> None:
    first = client.post("/api/v1/chats", json={"stock_code": "600519"}).json()
    second = client.post("/api/v1/chats", json={"stock_code": "603986"}).json()
    with db.connect() as connection:
        connection.executemany(
            "INSERT INTO chat_messages(id, chat_id, role, content, created_at, tool_traces) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("history-list-first", first["id"], "user", "第一条历史问题", "2099-01-01T00:00:00+00:00", "[]"),
                ("history-list-second", second["id"], "user", "第二条历史问题", "2099-01-02T00:00:00+00:00", "[]"),
            ],
        )

    history = client.get("/api/v1/chats?limit=2")
    assert history.status_code == 200
    assert [item["id"] for item in history.json()] == [second["id"], first["id"]]
    assert history.json()[0]["preview"] == "第二条历史问题"
    assert history.json()[0]["message_count"] == 1
    assert "messages" not in history.json()[0]

    assert client.delete(f"/api/v1/chats/{first['id']}").status_code == 204
    assert client.get(f"/api/v1/chats/{first['id']}").status_code == 404
    assert client.delete(f"/api/v1/chats/{first['id']}").status_code == 404
    with db.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM chat_messages WHERE id='history-list-first'"
        ).fetchone()[0] == 0

    deleted = client.post("/api/v1/chats/batch-delete", json={"ids": [second["id"]]})
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] == 1
    assert client.get(f"/api/v1/chats/{second['id']}").status_code == 404


def test_storage_clear_only_removes_requested_temporary_category() -> None:
    from stockllm.db import data_dir

    root = data_dir()
    market = root / "cache" / "market"
    external = root / "cache" / "external-links"
    market.mkdir(parents=True, exist_ok=True)
    external.mkdir(parents=True, exist_ok=True)
    (market / "quote.json").write_text("market", encoding="utf-8")
    (external / "article.json").write_text("article", encoding="utf-8")
    database_before = db.path.read_bytes()
    db.set_setting("storage.test", "preserve")

    response = client.post("/api/v1/system/storage/clear", json={"scopes": ["market"]})

    assert response.status_code == 200
    assert not (market / "quote.json").exists()
    assert (external / "article.json").exists()
    assert db.get_setting("storage.test", "") == "preserve"
    assert db.path.exists()
    assert len(db.path.read_bytes()) >= len(database_before)
    assert client.post("/api/v1/system/storage/clear", json={"scopes": ["../"]}).status_code == 422


def test_logs_are_structured_redacted_and_log_level_is_session_only() -> None:
    response = client.post("/api/v1/system/log-level", json={"level": "detailed"})
    assert response.json() == {"level": "detailed"}
    client.post("/api/v1/system/logs/client", json={
        "level": "error",
        "event": "window_error",
        "message": "authorization: Bearer secret-token sk-1234567890abcdef",
        "location": "http://localhost:5173/settings?desktop_token=secret",
    })
    entries = client.get("/api/v1/system/logs?limit=200&level=error").json()
    entry = next(item for item in entries if item.get("event") == "window_error")
    serialized = json.dumps(entry)
    assert "secret-token" not in serialized
    assert "sk-1234567890abcdef" not in serialized
    assert entry["location"] == "http://localhost:5173/settings"
    assert client.post("/api/v1/system/log-level", json={"level": "verbose"}).status_code == 422
    client.post("/api/v1/system/log-level", json={"level": "normal"})


def test_diagnostics_exports_respect_basic_and_detailed_boundaries(monkeypatch) -> None:
    db.set_setting("diagnostics.secret", "must-not-export")
    basic = client.post("/api/v1/system/diagnostics/export", json={"detail": "basic"})
    assert basic.status_code == 200
    with zipfile.ZipFile(BytesIO(basic.content)) as archive:
        assert set(archive.namelist()) == {"system.json", "logs.jsonl"}
        assert b"must-not-export" not in basic.content

    business_context = {"research_snapshots": [], "chats": [], "messages": [{"id": "diagnostic-message"}]}
    monkeypatch.setattr(db, "diagnostic_business_data", lambda: business_context)
    detailed = client.post("/api/v1/system/diagnostics/export", json={"detail": "detailed"})
    assert detailed.status_code == 200
    with zipfile.ZipFile(BytesIO(detailed.content)) as archive:
        assert "business-context.json" in archive.namelist()
        assert json.loads(archive.read("business-context.json")) == business_context
    assert b"must-not-export" not in detailed.content


def test_desktop_token_is_required_except_for_health(monkeypatch) -> None:
    monkeypatch.setenv("STOCKLLM_DESKTOP_TOKEN", "desktop-test-token")
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json() == {
        "status": "ok",
        "version": "0.2.0",
        "protocol_version": 1,
        "capabilities": [
            "desktop-session-token",
            "selection-events",
            "system-diagnostics",
        ],
    }
    preflight = client.options(
        "/api/v1/strategies",
        headers={
            "Origin": "http://tauri.localhost",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-stockllm-token",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://tauri.localhost"
    assert client.get("/api/v1/strategies").status_code == 401
    assert client.get("/api/v1/strategies?desktop_token=desktop-test-token").status_code == 401
    assert client.get(
        "/api/v1/strategies", headers={"X-StockLLM-Token": "desktop-test-token"}
    ).status_code == 200
    assert client.get(
        "/api/v1/selection-runs/missing/events?desktop_token=desktop-test-token"
    ).status_code == 404
