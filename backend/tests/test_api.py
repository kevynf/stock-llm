import os
import json
import zipfile
from io import BytesIO
from pathlib import Path

os.environ["STOCKLLM_DATA_DIR"] = str(Path(__file__).parent / ".test-data")
os.environ["STOCKLLM_ENABLE_DEMO"] = "1"

from fastapi.testclient import TestClient

from stockllm.main import app, db, service


client = TestClient(app)


def test_provider_status_uses_provider_and_child_item_fields(monkeypatch) -> None:
    class StubProvider:
        @staticmethod
        def source_statuses() -> list[dict]:
            return [{
                "id": "akshare-sina-spot",
                "provider": "AkShare",
                "name": "新浪财经 A 股行情",
                "description": "全市场最新价格、涨跌幅与成交额",
                "status": "available",
                "message": "探测成功",
                "checked_at": "2026-08-04T00:00:00+00:00",
            }]

    monkeypatch.setattr("stockllm.main.get_provider", lambda _: StubProvider())
    response = client.post("/api/v1/providers/status/check")
    assert response.status_code == 200
    item = response.json()[0]
    assert item["provider"] == "AkShare"
    assert item["name"] == "新浪财经 A 股行情"
    assert "adapter" not in item
    assert "content" not in item

    monkeypatch.setattr("stockllm.main.get_provider", lambda _: (_ for _ in ()).throw(RuntimeError("不应探测")))
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
    payload = client.get(f"/api/v1/selection-runs/{payload['id']}").json()
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
    payload = client.get(f"/api/v1/selection-runs/{payload['id']}").json()
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


def test_delete_selection_run_removes_related_records() -> None:
    response = client.post(
        "/api/v1/selection-runs",
        json={
            "risk_profile": "balanced", "horizon": "medium", "strategy": "trend",
            "as_of": "2026-08-01", "data_mode": "demo",
        },
    )
    run_id = response.json()["id"]
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
                "evidence_sources": {"price": "AkShare", "ma": "BaoStock"},
            }

    captured: list[dict] = []

    def answer(question: str, context: str, instruction: str, history: list[dict] | None = None) -> str:
        captured.append({"question": question, "context": context, "history": history or []})
        return "基于已提供证据的回答"

    monkeypatch.setattr("stockllm.service.get_provider", lambda mode: StubProvider())
    monkeypatch.setattr(service.gateway, "answer", answer)

    chat = client.post("/api/v1/chats", json={"stock_code": "603259"}).json()
    first = client.post(
        f"/api/v1/chats/{chat['id']}/messages",
        json={"content": "价格来自哪里？", "skill": "verify_sources"},
    )
    assert first.status_code == 200
    assert '"price": "AkShare"' in captured[0]["context"]
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

    monkeypatch.setattr("stockllm.service.get_provider", lambda mode: StubProvider())
    monkeypatch.setattr("stockllm.service.read_external_url", read)
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


def test_diagnostics_exports_respect_basic_and_detailed_boundaries() -> None:
    db.set_setting("diagnostics.secret", "must-not-export")
    basic = client.post("/api/v1/system/diagnostics/export", json={"detail": "basic"})
    assert basic.status_code == 200
    with zipfile.ZipFile(BytesIO(basic.content)) as archive:
        assert set(archive.namelist()) == {"system.json", "logs.jsonl"}
        assert b"must-not-export" not in basic.content

    detailed = client.post("/api/v1/system/diagnostics/export", json={"detail": "detailed"})
    assert detailed.status_code == 200
    with zipfile.ZipFile(BytesIO(detailed.content)) as archive:
        assert "business-context.json" in archive.namelist()
        assert "settings" not in archive.read("business-context.json").decode("utf-8")
    assert b"must-not-export" not in detailed.content


def test_desktop_token_is_required_except_for_health(monkeypatch) -> None:
    monkeypatch.setenv("STOCKLLM_DESKTOP_TOKEN", "desktop-test-token")
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json() == {
        "status": "ok",
        "version": "0.1.0",
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
