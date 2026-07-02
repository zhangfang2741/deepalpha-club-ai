"""供应链因果图谱系统集成测试。

覆盖：
  1. 实体归一化（纯单元）
  2. LLM 抽取 JSON 解析（纯单元）
  3. 转录抓取器级联（mock httpx）
  4. 摄取流水线（SQLite + mock LLM）
  5. REST API 端点（TestClient + SQLite + mock LLM）
"""

import json
from datetime import datetime
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

# ── SQLite 内存数据库 ─────────────────────────────────────────────────────────

_DB_URL = "sqlite:///file::memory:?cache=shared&uri=true"


@pytest.fixture(scope="session")
def test_engine():
    engine = create_engine(_DB_URL, connect_args={"check_same_thread": False})
    from app.models.graph_entity import GraphEntity  # noqa: F401
    from app.models.graph_fact import GraphFact  # noqa: F401
    from app.models.graph_source import SourceDocument  # noqa: F401
    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)


@pytest.fixture
def db(test_engine) -> Generator[Session, None, None]:
    with Session(test_engine) as session:
        yield session


# ─────────────────────────────────────────────────────────────────────────────
# 1. 实体归一化
# ─────────────────────────────────────────────────────────────────────────────

class TestNormalizer:
    def test_ticker_aliases(self):
        from app.services.graph.normalizer import normalize_entity_name
        assert normalize_entity_name("NVDA") == "NVIDIA"
        assert normalize_entity_name("nvidia corporation") == "NVIDIA"
        assert normalize_entity_name("Nvidia") == "NVIDIA"

    def test_product_aliases(self):
        from app.services.graph.normalizer import normalize_entity_name
        assert normalize_entity_name("H100") == "H100"
        assert normalize_entity_name("h100") == "H100"
        assert normalize_entity_name("hbm3e") == "HBM3E"
        assert normalize_entity_name("cowos") == "CoWoS"

    def test_technology_aliases(self):
        from app.services.graph.normalizer import normalize_entity_name
        assert normalize_entity_name("cuda") == "CUDA"
        assert normalize_entity_name("infiniband") == "InfiniBand"

    def test_unknown_returns_original(self):
        from app.services.graph.normalizer import normalize_entity_name
        assert normalize_entity_name("SomeUnknownEntity") == "SomeUnknownEntity"

    def test_guess_entity_type(self):
        from app.services.graph.normalizer import guess_entity_type
        assert guess_entity_type("NVIDIA") == "Company"
        assert guess_entity_type("H100") == "Product"
        assert guess_entity_type("CoWoS") == "Technology"
        assert guess_entity_type("Power Capacity") == "Resource"
        assert guess_entity_type("AI Training") == "Concept"


# ─────────────────────────────────────────────────────────────────────────────
# 2. LLM 抽取 JSON 解析
# ─────────────────────────────────────────────────────────────────────────────

class TestExtractor:
    def test_parse_object_format(self):
        from app.services.graph.extractor import _parse_llm_response
        raw = json.dumps({"facts": [
            {"source_entity": {"name": "NVIDIA", "type": "Company"},
             "relation": "HAS_PRODUCT",
             "target_entity": {"name": "H100", "type": "Product"},
             "evidence": "NVIDIA sells H100 GPUs",
             "confidence": 0.95,
             "event_time": None}
        ]})
        result = _parse_llm_response(raw)
        assert len(result) == 1
        assert result[0]["relation"] == "HAS_PRODUCT"

    def test_parse_array_format(self):
        from app.services.graph.extractor import _parse_llm_response
        raw = json.dumps([
            {"source_entity": {"name": "TSMC", "type": "Company"},
             "relation": "SUPPLIED_BY",
             "target_entity": {"name": "NVIDIA", "type": "Company"},
             "evidence": "TSMC supplies chips",
             "confidence": 0.9}
        ])
        result = _parse_llm_response(raw)
        assert len(result) == 1

    def test_parse_markdown_wrapped(self):
        from app.services.graph.extractor import _parse_llm_response
        raw = '```json\n{"facts": [{"source_entity": {"name": "CoWoS", "type": "Technology"}, "relation": "SUPPLIED_BY", "target_entity": {"name": "TSMC", "type": "Company"}, "evidence": "TSMC CoWoS", "confidence": 0.9}]}\n```'
        result = _parse_llm_response(raw)
        assert len(result) == 1

    def test_parse_empty(self):
        from app.services.graph.extractor import _parse_llm_response
        assert _parse_llm_response("[]") == []
        assert _parse_llm_response('{"facts": []}') == []

    def test_relation_type_mapping(self):
        from app.services.graph.extractor import _map_relation_type
        from app.models.graph_fact import RelationType
        assert _map_relation_type("HAS_PRODUCT") == RelationType.HAS_PRODUCT
        assert _map_relation_type("supplied_by") == RelationType.SUPPLIED_BY
        assert _map_relation_type("ENABLED_BY") == RelationType.ENABLED_BY
        assert _map_relation_type("constrained_by") == RelationType.CONSTRAINED_BY
        assert _map_relation_type("unknown_relation") is None

    def test_event_time_parsing(self):
        from app.services.graph.extractor import _parse_event_time
        assert _parse_event_time("2024-Q3") == datetime(2024, 7, 1)
        assert _parse_event_time("2024-Q1") == datetime(2024, 1, 1)
        assert _parse_event_time("2024-Q4") == datetime(2024, 10, 1)
        assert _parse_event_time("2024-01-15") == datetime(2024, 1, 15)
        assert _parse_event_time(None) is None
        assert _parse_event_time("invalid") is None

    def test_full_parse_extracted_facts(self):
        from app.services.graph.extractor import parse_extracted_facts
        from app.models.graph_fact import RelationType
        raw = [
            {"source_entity": {"name": "NVIDIA", "type": "Company"},
             "relation": "HAS_PRODUCT",
             "target_entity": {"name": "H100", "type": "Product"},
             "evidence": "NVIDIA sells H100 GPUs to hyperscalers",
             "confidence": 0.95,
             "event_time": "2024-Q3"},
            {"source_entity": {"name": "H100", "type": "Product"},
             "relation": "CONSTRAINED_BY",
             "target_entity": {"name": "CoWoS", "type": "Resource"},
             "evidence": "H100 supply constrained by CoWoS packaging capacity",
             "confidence": 0.88,
             "event_time": None},
        ]
        facts = parse_extracted_facts(raw)
        assert len(facts) == 2
        assert facts[0].source_name == "NVIDIA"
        assert facts[0].target_name == "H100"
        assert facts[0].relation == RelationType.HAS_PRODUCT
        assert facts[0].confidence == 0.95
        assert facts[0].event_time == datetime(2024, 7, 1)
        assert facts[1].relation == RelationType.CONSTRAINED_BY
        assert facts[1].event_time is None


# ─────────────────────────────────────────────────────────────────────────────
# 3. 转录抓取器（mock httpx）
# ─────────────────────────────────────────────────────────────────────────────

class TestTranscriptScraper:
    def _make_response(self, json_data=None, text=None, status=200):
        mock = MagicMock()
        mock.status_code = status
        mock.raise_for_status = MagicMock()
        if json_data is not None:
            mock.json.return_value = json_data
        if text is not None:
            mock.text = text
        return mock

    @pytest.mark.asyncio
    async def test_alpha_vantage_success(self):
        from app.services.graph.transcript_scraper import TranscriptScraper
        scraper = TranscriptScraper()

        av_payload = {
            "symbol": "NVDA",
            "quarter": "2024Q3",
            "transcript": [
                {"name": "Jensen Huang", "content": "We delivered record revenue driven by data center demand for H100."},
                {"name": "Colette Kress", "content": "Data center revenue was $14.5 billion, up 154% year-over-year."},
            ] * 50,  # 保证超过 500 字符
        }
        mock_resp = self._make_response(json_data=av_payload)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            text = await scraper._fetch_alpha_vantage("NVDA", 2024, 3)

        assert text is not None
        assert "Jensen Huang" in text
        assert len(text) > 500

    @pytest.mark.asyncio
    async def test_alpha_vantage_empty_falls_through(self):
        from app.services.graph.transcript_scraper import TranscriptScraper
        scraper = TranscriptScraper()

        av_payload = {"symbol": "NVDA", "quarter": "2024Q3", "transcript": []}
        mock_resp = self._make_response(json_data=av_payload)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            text = await scraper._fetch_alpha_vantage("NVDA", 2024, 3)

        assert text is None

    @pytest.mark.asyncio
    async def test_motley_fool_success(self):
        from app.services.graph.transcript_scraper import TranscriptScraper
        scraper = TranscriptScraper()

        search_payload = {
            "solrResults": {
                "results": [
                    {"url": "/earnings/call-transcripts/2024/08/28/nvidia-nvda-q3-2024-earnings-call-transcript/"}
                ]
            }
        }
        transcript_html = """
        <html><body>
        <article>
        <p>Jensen Huang - CEO: Good afternoon, everyone. We are pleased to report record quarterly revenue.</p>
        <p>Our data center business continued its strong momentum, with H100 demand exceeding supply.</p>
        <p>TSMC CoWoS packaging capacity remains a key constraint that we are working to expand.</p>
        <p>We expect continued strong demand from hyperscalers including Microsoft, Meta, and Google.</p>
        </article>
        </body></html>
        """ * 10  # 保证超过 500 字符

        search_resp = self._make_response(json_data=search_payload)
        page_resp = self._make_response(text=transcript_html)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(side_effect=[search_resp, page_resp])
            mock_client_cls.return_value = mock_client

            text = await scraper._fetch_motley_fool("NVDA", 2024, 3)

        assert text is not None
        assert "Jensen Huang" in text
        assert len(text) > 500

    @pytest.mark.asyncio
    async def test_cascade_falls_through_to_motley_fool(self):
        """AV 失败时级联到 Motley Fool。"""
        from app.services.graph.transcript_scraper import TranscriptScraper
        scraper = TranscriptScraper()

        long_text = "Jensen Huang: We delivered record revenue. " * 30

        with (
            patch.object(scraper, "_fetch_alpha_vantage", new=AsyncMock(return_value=None)),
            patch.object(scraper, "_fetch_motley_fool", new=AsyncMock(return_value=long_text)),
            patch.object(scraper, "_fetch_sec_8k", new=AsyncMock(return_value=None)),
        ):
            result = await scraper.get_transcript("NVDA", 2024, 3)

        assert result is not None
        assert "Jensen Huang" in result
        assert "EARNINGS CALL TRANSCRIPT" in result
        assert "Motley Fool" in result

    @pytest.mark.asyncio
    async def test_cascade_all_fail_returns_none(self):
        from app.services.graph.transcript_scraper import TranscriptScraper
        scraper = TranscriptScraper()

        with (
            patch.object(scraper, "_fetch_alpha_vantage", new=AsyncMock(return_value=None)),
            patch.object(scraper, "_fetch_motley_fool", new=AsyncMock(return_value=None)),
            patch.object(scraper, "_fetch_sec_8k", new=AsyncMock(return_value=None)),
        ):
            result = await scraper.get_transcript("NVDA", 2024, 3)

        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# 4. 摄取流水线（SQLite + mock LLM）
# ─────────────────────────────────────────────────────────────────────────────

_SAMPLE_TRANSCRIPT = """
EARNINGS CALL TRANSCRIPT
Company: NVDA | Period: 2024 Q3
============================================================

Jensen Huang - CEO: Good afternoon. We reported record revenue of $35.1 billion, up 94% year-over-year.
Our data center segment revenue was $30.8 billion, driven by strong demand for NVIDIA H100 and H200 GPUs.

TSMC manufactures our Blackwell chips using CoWoS advanced packaging technology.
SK Hynix supplies the HBM3E memory integrated into our H200 GPU.
H100 production remains constrained by CoWoS packaging capacity at TSMC.

Microsoft, Meta, and Google are our largest hyperscaler customers, deploying our GPUs for AI training workloads.
The demand for large language model training continues to drive infrastructure investment.

Colette Kress - CFO: NVIDIA's H100 enabled the next wave of generative AI applications.
CoWoS capacity supplied by TSMC is ramping to meet demand throughout fiscal year 2025.
"""

_MOCK_LLM_RESPONSE = json.dumps({"facts": [
    {"source_entity": {"name": "NVIDIA", "type": "Company"},
     "relation": "HAS_PRODUCT",
     "target_entity": {"name": "H100", "type": "Product"},
     "evidence": "data center segment driven by strong demand for NVIDIA H100",
     "confidence": 0.95,
     "event_time": "2024-Q3"},
    {"source_entity": {"name": "CoWoS", "type": "Technology"},
     "relation": "SUPPLIED_BY",
     "target_entity": {"name": "TSMC", "type": "Company"},
     "evidence": "TSMC manufactures our Blackwell chips using CoWoS advanced packaging technology",
     "confidence": 0.93,
     "event_time": None},
    {"source_entity": {"name": "H100", "type": "Product"},
     "relation": "CONSTRAINED_BY",
     "target_entity": {"name": "CoWoS", "type": "Resource"},
     "evidence": "H100 production remains constrained by CoWoS packaging capacity at TSMC",
     "confidence": 0.91,
     "event_time": "2024-Q3"},
]})


def _mock_llm(response_text: str):
    """创建返回固定文本的 mock LLM 客户端。"""
    llm = MagicMock()
    msg = MagicMock()
    msg.content = response_text
    llm.ainvoke = AsyncMock(return_value=msg)
    return llm


@pytest.mark.asyncio
async def test_pipeline_run_end_to_end(test_engine):
    """完整流水线：文本 → 切片 → LLM 抽取 → SQLite 存储。"""
    from app.models.graph_source import DocumentStatus, DocumentType, SourceDocument
    from app.services.graph.pipeline import run_ingest_pipeline

    doc = SourceDocument(
        url="transcript://NVDA/2024Q3",
        document_type=DocumentType.EARNINGS_CALL,
        ticker="NVDA",
        company_name="NVIDIA",
        title="NVDA Earnings Call 2024 Q3",
        section="Full Transcript",
    )
    with Session(test_engine) as session:
        session.add(doc)
        session.commit()
        session.refresh(doc)

    llm = _mock_llm(_MOCK_LLM_RESPONSE)

    with patch("app.services.graph.pipeline.sync_engine", test_engine):
        count = await run_ingest_pipeline(doc, llm, raw_text=_SAMPLE_TRANSCRIPT)

    assert count > 0, "应该至少存入一条事实"

    from sqlmodel import select
    from app.models.graph_entity import GraphEntity
    from app.models.graph_fact import GraphFact
    with Session(test_engine) as session:
        entities = session.exec(select(GraphEntity)).all()
        facts = session.exec(select(GraphFact)).all()

    entity_names = {e.name for e in entities}
    assert "NVIDIA" in entity_names
    assert "H100" in entity_names
    assert "TSMC" in entity_names

    assert len(facts) > 0

    updated_doc = None
    with Session(test_engine) as session:
        updated_doc = session.get(SourceDocument, doc.id)
    assert updated_doc.status == DocumentStatus.DONE
    assert updated_doc.fact_count > 0


@pytest.mark.asyncio
async def test_ingest_raw_text(test_engine):
    """ingest_raw_text 函数：直接传文本，自动建 doc 并跑流水线。"""
    from app.services.graph.pipeline import ingest_raw_text
    from app.models.graph_source import DocumentType

    llm = _mock_llm(_MOCK_LLM_RESPONSE)

    with patch("app.services.graph.pipeline.sync_engine", test_engine):
        count, doc_id = await ingest_raw_text(
            raw_text=_SAMPLE_TRANSCRIPT,
            document_type=DocumentType.EARNINGS_CALL,
            llm_client=llm,
            ticker="NVDA",
            title="NVDA Q3 2024 Manual Test",
        )

    assert doc_id is not None
    assert count > 0


@pytest.mark.asyncio
async def test_ingest_too_short_text_rejected():
    """文本过短时 ingest_raw_text 直接拒绝，返回 (0, None)。"""
    from app.services.graph.pipeline import ingest_raw_text
    from app.models.graph_source import DocumentType

    count, doc_id = await ingest_raw_text(
        raw_text="Too short.",
        document_type=DocumentType.EARNINGS_CALL,
        llm_client=MagicMock(),
    )
    assert count == 0
    assert doc_id is None


# ─────────────────────────────────────────────────────────────────────────────
# 5. API 端点（TestClient + SQLite）
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def api_client(test_engine):
    """FastAPI TestClient，db 依赖指向 SQLite 内存库。"""
    from app.main import app
    from app.db.session import get_sync_session

    def _override_session():
        with Session(test_engine) as session:
            yield session

    app.dependency_overrides[get_sync_session] = _override_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


class TestSupplyChainAPI:
    def test_stats_endpoint(self, api_client):
        resp = api_client.get("/api/v1/supply-chain/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "entities" in data
        assert "facts" in data
        assert "total_entities" in data
        assert "total_facts" in data

    def test_list_entities_empty(self, api_client):
        resp = api_client.get("/api/v1/supply-chain/entities")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_create_entity(self, api_client):
        payload = {
            "entity_type": "Company",
            "name": "Test Corp",
            "ticker": "TEST",
            "description": "A test company",
        }
        resp = api_client.post("/api/v1/supply-chain/entities", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Corp"
        assert data["ticker"] == "TEST"
        assert "id" in data

    def test_create_entity_duplicate_rejected(self, api_client):
        payload = {"entity_type": "Company", "name": "DupCorp"}
        api_client.post("/api/v1/supply-chain/entities", json=payload)
        resp = api_client.post("/api/v1/supply-chain/entities", json=payload)
        assert resp.status_code == 409

    def test_get_entity_by_id(self, api_client):
        create_resp = api_client.post(
            "/api/v1/supply-chain/entities",
            json={"entity_type": "Product", "name": "H200 GPU"},
        )
        entity_id = create_resp.json()["id"]
        resp = api_client.get(f"/api/v1/supply-chain/entities/{entity_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "H200 GPU"

    def test_get_entity_not_found(self, api_client):
        import uuid
        resp = api_client.get(f"/api/v1/supply-chain/entities/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_create_and_list_facts(self, api_client):
        src = api_client.post(
            "/api/v1/supply-chain/entities",
            json={"entity_type": "Company", "name": "FactSrc Co"},
        ).json()
        tgt = api_client.post(
            "/api/v1/supply-chain/entities",
            json={"entity_type": "Product", "name": "FactTgt Product"},
        ).json()

        fact_payload = {
            "source_entity_id": src["id"],
            "target_entity_id": tgt["id"],
            "relation_type": "HAS_PRODUCT",
            "evidence_text": "FactSrc Co manufactures FactTgt Product.",
            "confidence": 0.9,
        }
        resp = api_client.post("/api/v1/supply-chain/facts", json=fact_payload)
        assert resp.status_code == 201
        fact = resp.json()
        assert fact["relation_type"] == "HAS_PRODUCT"
        assert fact["source_entity_name"] == "FactSrc Co"
        assert fact["target_entity_name"] == "FactTgt Product"

    def test_get_graph_data(self, api_client):
        resp = api_client.get("/api/v1/supply-chain/graph")
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert "edges" in data
        assert "total_entities" in data
        assert "total_facts" in data

    def test_get_graph_filter_by_entity_type(self, api_client):
        resp = api_client.get("/api/v1/supply-chain/graph?entity_types=Company")
        assert resp.status_code == 200

    def test_ingest_text_endpoint(self, api_client):
        """POST /ingest/text 提交原始文本，返回 202 + doc_id。"""
        payload = {
            "text": _SAMPLE_TRANSCRIPT,
            "document_type": "earnings_call",
            "ticker": "NVDA",
            "title": "NVDA Q3 2024 Test",
        }
        with patch("app.api.v1.supply_chain._get_llm", return_value=_mock_llm(_MOCK_LLM_RESPONSE)):
            resp = api_client.post("/api/v1/supply-chain/ingest/text", json=payload)
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "queued"
        assert "doc_id" in data

    def test_ingest_text_too_short_rejected(self, api_client):
        payload = {
            "text": "too short",
            "document_type": "earnings_call",
        }
        resp = api_client.post("/api/v1/supply-chain/ingest/text", json=payload)
        assert resp.status_code == 422  # Pydantic min_length 验证

    def test_bottleneck_analysis(self, api_client):
        resp = api_client.get("/api/v1/supply-chain/analysis/bottlenecks")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_demand_chain_not_found(self, api_client):
        resp = api_client.get("/api/v1/supply-chain/analysis/demand-chain/NonExistentConcept")
        assert resp.status_code == 404

    def test_list_documents(self, api_client):
        resp = api_client.get("/api/v1/supply-chain/documents")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


# ─────────────────────────────────────────────────────────────────────────────
# 6. 种子数据集完整性与注入（app/services/graph/seed.py）
# ─────────────────────────────────────────────────────────────────────────────

class TestSeedDataset:
    """校验种子数据集自洽：类型合法、事实两端实体均已定义、覆盖全部关系。"""

    def _load(self):
        from app.services.graph import seed
        return seed

    def test_entity_types_valid(self):
        from app.models.graph_entity import EntityType
        mod = self._load()
        valid = {e.value for e in EntityType}
        for name, etype, _ticker, _desc in mod.ENTITIES:
            assert etype in valid, f"非法实体类型 {etype}（{name}）"

    def test_entity_names_unique(self):
        mod = self._load()
        names = [e[0] for e in mod.ENTITIES]
        assert len(names) == len(set(names)), "存在重复实体名称"

    def test_facts_reference_known_entities(self):
        mod = self._load()
        names = {e[0] for e in mod.ENTITIES}
        for src, _rel, tgt, *_ in mod.FACTS:
            assert src in names, f"事实来源实体未定义：{src}"
            assert tgt in names, f"事实目标实体未定义：{tgt}"

    def test_facts_cover_all_relations(self):
        from app.models.graph_fact import RelationType
        mod = self._load()
        used = {f[1] for f in mod.FACTS}
        for rel in RelationType:
            assert rel.value in used, f"种子缺少关系类型 {rel.value}"

    def test_facts_confidence_in_range(self):
        mod = self._load()
        for _src, _rel, _tgt, _ev, conf, _t in mod.FACTS:
            assert 0.0 <= conf <= 1.0

    def _fresh_session(self):
        from app.models.graph_entity import GraphEntity  # noqa: F401
        from app.models.graph_fact import GraphFact  # noqa: F401
        from app.models.graph_source import SourceDocument  # noqa: F401

        engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
        SQLModel.metadata.create_all(engine)
        return Session(engine)

    def test_seed_inserts_and_is_idempotent(self):
        from app.models.graph_entity import GraphEntity
        from app.models.graph_fact import GraphFact
        from sqlmodel import select

        from app.services.graph.seed import ENTITIES, FACTS, seed_supply_chain_graph

        with self._fresh_session() as session:
            created_e, created_f = seed_supply_chain_graph(session)
            assert created_e == len(ENTITIES)
            assert created_f == len(FACTS)

            # 再次注入（force 跳过空库守卫）不应产生重复
            again_e, again_f = seed_supply_chain_graph(session, force=True)
            assert again_e == 0
            assert again_f == 0

            assert len(session.exec(select(GraphEntity)).all()) == len(ENTITIES)
            assert len(session.exec(select(GraphFact)).all()) == len(FACTS)

    def test_seed_skips_when_graph_not_empty(self):
        from app.models.graph_entity import EntityType, GraphEntity
        from app.services.graph.seed import seed_supply_chain_graph

        with self._fresh_session() as session:
            session.add(GraphEntity(entity_type=EntityType.COMPANY, name="Preexisting"))
            session.commit()

            created_e, created_f = seed_supply_chain_graph(session)
            assert created_e == 0
            assert created_f == 0


# ─────────────────────────────────────────────────────────────────────────────
# 7. 通用化与图谱查询增强（多产业支持 / 时间筛选 / 重要度排序）
# ─────────────────────────────────────────────────────────────────────────────

def _isolated_session():
    from app.models.graph_entity import GraphEntity  # noqa: F401
    from app.models.graph_fact import GraphFact  # noqa: F401
    from app.models.graph_source import SourceDocument  # noqa: F401

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


class TestNormalizerGeneralization:
    def test_word_boundary_avoids_false_substring(self):
        from app.services.graph.normalizer import normalize_entity_name
        # "Inteliquent" 含子串 "intel" 但不应被误配为 Intel
        assert normalize_entity_name("Inteliquent") == "Inteliquent"

    def test_unknown_company_passes_through(self):
        from app.services.graph.normalizer import normalize_entity_name
        # 非半导体行业的公司原样返回，证明对任意产业链安全
        assert normalize_entity_name("Eli Lilly") == "Eli Lilly"
        assert normalize_entity_name("CATL") == "CATL"

    def test_known_alias_still_normalizes(self):
        from app.services.graph.normalizer import normalize_entity_name
        assert normalize_entity_name("nvidia corporation") == "NVIDIA"


class TestGraphQuery:
    def test_since_keeps_recent_and_structural_facts(self):
        from datetime import datetime
        from app.models.graph_entity import EntityType, GraphEntity
        from app.models.graph_fact import GraphFact, RelationType
        from app.schemas.supply_chain import GraphQueryParams
        from app.services.graph.query import get_graph_data

        with _isolated_session() as s:
            a = GraphEntity(entity_type=EntityType.COMPANY, name="A")
            b = GraphEntity(entity_type=EntityType.PRODUCT, name="B")
            c = GraphEntity(entity_type=EntityType.RESOURCE, name="C")
            s.add_all([a, b, c])
            s.commit()
            for e in (a, b, c):
                s.refresh(e)

            s.add_all([
                GraphFact(source_entity_id=a.id, target_entity_id=b.id, relation_type=RelationType.HAS_PRODUCT,
                          evidence_text="old", confidence=0.9, event_time=datetime(2020, 1, 1)),
                GraphFact(source_entity_id=b.id, target_entity_id=c.id, relation_type=RelationType.CONSTRAINED_BY,
                          evidence_text="recent", confidence=0.9, event_time=datetime(2025, 1, 1)),
                GraphFact(source_entity_id=a.id, target_entity_id=c.id, relation_type=RelationType.SUPPLIED_BY,
                          evidence_text="structural", confidence=0.9, event_time=None),
            ])
            s.commit()

            data = get_graph_data(s, GraphQueryParams(since=datetime(2024, 1, 1), limit=50))
            texts = {e.evidence_text for e in data.edges}
            assert "recent" in texts        # 2025 的事实保留
            assert "structural" in texts    # 无 event_time 的结构性事实保留
            assert "old" not in texts        # 2020 的事实被过滤

    def test_degree_ordering_drops_isolated_when_limited(self):
        from app.models.graph_entity import EntityType, GraphEntity
        from app.models.graph_fact import GraphFact, RelationType
        from app.schemas.supply_chain import GraphQueryParams
        from app.services.graph.query import get_graph_data

        with _isolated_session() as s:
            hub = GraphEntity(entity_type=EntityType.COMPANY, name="Hub")
            leaf1 = GraphEntity(entity_type=EntityType.PRODUCT, name="Leaf1")
            leaf2 = GraphEntity(entity_type=EntityType.PRODUCT, name="Leaf2")
            lonely = GraphEntity(entity_type=EntityType.CONCEPT, name="Lonely")
            s.add_all([hub, leaf1, leaf2, lonely])
            s.commit()
            for e in (hub, leaf1, leaf2, lonely):
                s.refresh(e)

            s.add_all([
                GraphFact(source_entity_id=hub.id, target_entity_id=leaf1.id, relation_type=RelationType.HAS_PRODUCT,
                          evidence_text="x", confidence=0.9),
                GraphFact(source_entity_id=hub.id, target_entity_id=leaf2.id, relation_type=RelationType.HAS_PRODUCT,
                          evidence_text="y", confidence=0.9),
            ])
            s.commit()

            # limit=3：按连接度取前 3，孤立实体（度=0）应被排除
            data = get_graph_data(s, GraphQueryParams(limit=3))
            names = {n.name for n in data.nodes}
            assert "Hub" in names
            assert "Lonely" not in names


class TestDemandChain:
    def test_includes_concept_level_constraint(self):
        from app.models.graph_entity import EntityType, GraphEntity
        from app.models.graph_fact import GraphFact, RelationType
        from app.services.graph.query import get_demand_chain

        with _isolated_session() as s:
            concept = GraphEntity(entity_type=EntityType.CONCEPT, name="AI Training")
            tech = GraphEntity(entity_type=EntityType.TECHNOLOGY, name="HBM3E")
            power = GraphEntity(entity_type=EntityType.RESOURCE, name="Power Capacity")
            s.add_all([concept, tech, power])
            s.commit()
            for e in (concept, tech, power):
                s.refresh(e)

            s.add_all([
                GraphFact(source_entity_id=concept.id, target_entity_id=tech.id,
                          relation_type=RelationType.ENABLED_BY, evidence_text="a", confidence=0.9),
                # 概念自身的瓶颈，旧逻辑会漏掉
                GraphFact(source_entity_id=concept.id, target_entity_id=power.id,
                          relation_type=RelationType.CONSTRAINED_BY, evidence_text="b", confidence=0.9),
            ])
            s.commit()

            chain = get_demand_chain(s, "AI Training")
            assert chain is not None
            constrained_names = {e.name for e in chain.constrained_resources}
            assert "Power Capacity" in constrained_names


class TestBottleneckDescription:
    def test_chinese_description_generated(self):
        from app.models.graph_entity import EntityType, GraphEntity
        from app.models.graph_fact import GraphFact, RelationType
        from app.services.graph.query import get_bottleneck_report

        with _isolated_session() as s:
            power = GraphEntity(entity_type=EntityType.RESOURCE, name="Power Capacity")
            p1 = GraphEntity(entity_type=EntityType.CONCEPT, name="AI Training")
            p2 = GraphEntity(entity_type=EntityType.CONCEPT, name="AI Inference")
            p3 = GraphEntity(entity_type=EntityType.CONCEPT, name="Data Center")
            s.add_all([power, p1, p2, p3])
            s.commit()
            for e in (power, p1, p2, p3):
                s.refresh(e)

            s.add_all([
                GraphFact(source_entity_id=p.id, target_entity_id=power.id,
                          relation_type=RelationType.CONSTRAINED_BY, evidence_text="e", confidence=0.9)
                for p in (p1, p2, p3)
            ])
            s.commit()

            reports = get_bottleneck_report(s)
            assert len(reports) == 1
            desc = reports[0].description
            assert "Power Capacity" in desc
            assert "核心瓶颈" in desc          # 3 个约束 → 高度集中的核心瓶颈
            assert "资源" in desc              # 类型中文称谓
            assert "AI Training" in desc       # 受制方


class TestFactsDocFilter:
    def test_filter_facts_by_doc_id(self):
        import uuid as _uuid
        from app.api.v1.supply_chain import list_facts
        from app.models.graph_entity import EntityType, GraphEntity
        from app.models.graph_fact import GraphFact, RelationType

        with _isolated_session() as s:
            a = GraphEntity(entity_type=EntityType.COMPANY, name="A")
            b = GraphEntity(entity_type=EntityType.PRODUCT, name="B")
            s.add_all([a, b])
            s.commit()
            s.refresh(a)
            s.refresh(b)

            doc1, doc2 = _uuid.uuid4(), _uuid.uuid4()
            s.add_all([
                GraphFact(source_entity_id=a.id, target_entity_id=b.id, relation_type=RelationType.HAS_PRODUCT,
                          evidence_text="from doc1", confidence=0.9, source_doc_id=doc1),
                GraphFact(source_entity_id=a.id, target_entity_id=b.id, relation_type=RelationType.SUPPLIED_BY,
                          evidence_text="from doc2", confidence=0.9, source_doc_id=doc2),
            ])
            s.commit()

            res = list_facts(relation_type=None, min_confidence=0.0, doc_id=doc1, limit=100, session=s)
            assert {f.evidence_text for f in res} == {"from doc1"}


@pytest.mark.asyncio
async def test_pipeline_tracks_processed_chunks(test_engine):
    """run_ingest_pipeline 完成后 processed_chunks 应等于 chunk_count（进度到 100%）。"""
    from app.services.graph.pipeline import run_ingest_pipeline
    from app.models.graph_source import DocumentType, SourceDocument

    doc = SourceDocument(url="text://prog-test", document_type=DocumentType.EARNINGS_CALL, ticker="PROG")
    with Session(test_engine) as s:
        s.add(doc)
        s.commit()
        s.refresh(doc)

    llm = _mock_llm(_MOCK_LLM_RESPONSE)
    with patch("app.services.graph.pipeline.sync_engine", test_engine):
        await run_ingest_pipeline(doc, llm, raw_text=_SAMPLE_TRANSCRIPT)

    with Session(test_engine) as s:
        updated = s.get(SourceDocument, doc.id)
    assert updated.chunk_count > 0
    assert updated.processed_chunks == updated.chunk_count


def test_find_cached_done(test_engine):
    """缓存去重：按 cache_key 命中已完成文档返回 (id, fact_count)，未命中返回 None。"""
    from app.services.graph.pipeline import _find_cached_done
    from app.models.graph_source import DocumentStatus, DocumentType, SourceDocument

    doc = SourceDocument(
        url="x://cache", document_type=DocumentType.EARNINGS_CALL, ticker="CACHE",
        status=DocumentStatus.DONE, fact_count=7, cache_key="ec:CACHE:2024:1",
    )
    with Session(test_engine) as s:
        s.add(doc)
        s.commit()
        s.refresh(doc)
        did = str(doc.id)

    with patch("app.services.graph.pipeline.sync_engine", test_engine):
        hit = _find_cached_done("ec:CACHE:2024:1")
        miss = _find_cached_done("ec:NOPE:2024:1")

    assert hit == (did, 7)
    assert miss is None


# ─────────────────────────────────────────────────────────────────────────────
# 8. FinReflectKG 反思式抽取（reflection_graph）
# ─────────────────────────────────────────────────────────────────────────────

_REFLECT_CHUNK = (
    "NVIDIA reported record data center revenue driven by strong demand for its H100 GPU. "
    "TSMC manufactures the H100 using CoWoS advanced packaging technology. "
    "H100 production remains constrained by CoWoS packaging capacity."
)


class TestCheckRules:
    """确定性规则检查（对应论文 rule-based compliance policies）。"""

    def test_valid_fact_passes(self):
        from app.services.graph.reflection_graph import check_fact_rules
        fact = {
            "source_entity": {"name": "NVIDIA", "type": "Company"},
            "relation": "HAS_PRODUCT",
            "target_entity": {"name": "H100", "type": "Product"},
            "evidence": "strong demand for its H100 GPU",
            "confidence": 0.95,
        }
        assert check_fact_rules(fact, _REFLECT_CHUNK) == []

    def test_invalid_relation_flagged(self):
        from app.services.graph.reflection_graph import check_fact_rules
        fact = {
            "source_entity": {"name": "NVIDIA", "type": "Company"},
            "relation": "MADE_UP_RELATION",
            "target_entity": {"name": "H100", "type": "Product"},
            "evidence": "strong demand for its H100 GPU",
            "confidence": 0.9,
        }
        violations = check_fact_rules(fact, _REFLECT_CHUNK)
        assert any("非法关系类型" in v for v in violations)

    def test_type_signature_mismatch_flagged(self):
        from app.services.graph.reflection_graph import check_fact_rules
        # HAS_PRODUCT 要求 Company→Product，这里 Product→Company 非法
        fact = {
            "source_entity": {"name": "H100", "type": "Product"},
            "relation": "HAS_PRODUCT",
            "target_entity": {"name": "NVIDIA", "type": "Company"},
            "evidence": "strong demand for its H100 GPU",
            "confidence": 0.9,
        }
        violations = check_fact_rules(fact, _REFLECT_CHUNK)
        assert any("类型组合不合法" in v for v in violations)

    def test_self_loop_flagged(self):
        from app.services.graph.reflection_graph import check_fact_rules
        fact = {
            "source_entity": {"name": "NVIDIA", "type": "Company"},
            "relation": "HAS_PRODUCT",
            "target_entity": {"name": "NVIDIA", "type": "Product"},
            "evidence": "NVIDIA",
            "confidence": 0.9,
        }
        violations = check_fact_rules(fact, _REFLECT_CHUNK)
        assert any("自环" in v for v in violations)

    def test_ungrounded_evidence_flagged(self):
        from app.services.graph.reflection_graph import check_fact_rules
        fact = {
            "source_entity": {"name": "NVIDIA", "type": "Company"},
            "relation": "HAS_PRODUCT",
            "target_entity": {"name": "H100", "type": "Product"},
            "evidence": "The quarterly dividend was raised amid favorable macroeconomic tailwinds worldwide",
            "confidence": 0.9,
        }
        violations = check_fact_rules(fact, _REFLECT_CHUNK)
        assert any("证据未接地" in v for v in violations)

    def test_confidence_out_of_range_flagged(self):
        from app.services.graph.reflection_graph import check_fact_rules
        fact = {
            "source_entity": {"name": "NVIDIA", "type": "Company"},
            "relation": "HAS_PRODUCT",
            "target_entity": {"name": "H100", "type": "Product"},
            "evidence": "strong demand for its H100 GPU",
            "confidence": 1.7,
        }
        violations = check_fact_rules(fact, _REFLECT_CHUNK)
        assert any("越界" in v for v in violations)

    def test_compliance_score_and_filter(self):
        from app.services.graph.reflection_graph import compliance_score, filter_compliant_facts
        good = {
            "source_entity": {"name": "NVIDIA", "type": "Company"},
            "relation": "HAS_PRODUCT",
            "target_entity": {"name": "H100", "type": "Product"},
            "evidence": "strong demand for its H100 GPU",
            "confidence": 0.95,
        }
        bad = {
            "source_entity": {"name": "NVIDIA", "type": "Company"},
            "relation": "MADE_UP",
            "target_entity": {"name": "H100", "type": "Product"},
            "evidence": "strong demand for its H100 GPU",
            "confidence": 0.9,
        }
        facts = [good, bad]
        assert compliance_score(facts, _REFLECT_CHUNK) == 0.5
        clean = filter_compliant_facts(facts, _REFLECT_CHUNK)
        assert len(clean) == 1
        assert clean[0]["relation"] == "HAS_PRODUCT"


class TestReflectionGraph:
    """反思图端到端：抽取→评审→修正闭环（mock LLM 按角色返回）。"""

    def _role_llm(self, extract_resp: str, critic_resp: str, refine_resp: str):
        """按 system prompt 判定角色，返回对应响应的 mock LLM。"""
        from app.services.graph.reflection_graph import _CRITIC_SYSTEM_PROMPT

        def _dispatch(messages):
            system_text = messages[0].content
            user_text = messages[1].content
            if system_text == _CRITIC_SYSTEM_PROMPT:
                resp = critic_resp
            elif "MUST fix" in user_text:
                resp = refine_resp
            else:
                resp = extract_resp
            m = MagicMock()
            m.content = resp
            return m

        llm = MagicMock()
        llm.ainvoke = AsyncMock(side_effect=_dispatch)
        return llm

    @pytest.mark.asyncio
    async def test_approved_first_pass_no_refine(self):
        """评审通过则不进入修正，直接返回。"""
        from app.services.graph.reflection_graph import extract_facts_with_reflection

        extract_resp = json.dumps({"facts": [{
            "source_entity": {"name": "NVIDIA", "type": "Company"},
            "relation": "HAS_PRODUCT",
            "target_entity": {"name": "H100", "type": "Product"},
            "evidence": "strong demand for its H100 GPU",
            "confidence": 0.95,
        }]})
        critic_resp = json.dumps({"approve": True, "issues": [], "missing": []})
        refine_resp = json.dumps({"facts": []})  # 不应被调用

        llm = self._role_llm(extract_resp, critic_resp, refine_resp)
        facts = await extract_facts_with_reflection(_REFLECT_CHUNK, "NVIDIA 10-K", llm, max_iterations=2)

        assert len(facts) == 1
        assert facts[0].source_name == "NVIDIA"
        assert facts[0].target_name == "H100"

    @pytest.mark.asyncio
    async def test_reflection_fixes_bad_triple(self):
        """初次抽取含非法三元组，经评审+修正后得到合规结果。"""
        from app.services.graph.reflection_graph import extract_facts_with_reflection

        # 初抽取：关系非法（会被规则命中，评审不通过）
        extract_resp = json.dumps({"facts": [{
            "source_entity": {"name": "NVIDIA", "type": "Company"},
            "relation": "MADE_UP_RELATION",
            "target_entity": {"name": "H100", "type": "Product"},
            "evidence": "strong demand for its H100 GPU",
            "confidence": 0.9,
        }]})
        critic_resp = json.dumps({"approve": False, "issues": ["triple #0 relation invalid"], "missing": []})
        # 修正：改为合法关系
        refine_resp = json.dumps({"facts": [{
            "source_entity": {"name": "NVIDIA", "type": "Company"},
            "relation": "HAS_PRODUCT",
            "target_entity": {"name": "H100", "type": "Product"},
            "evidence": "strong demand for its H100 GPU",
            "confidence": 0.9,
        }]})

        llm = self._role_llm(extract_resp, critic_resp, refine_resp)
        facts = await extract_facts_with_reflection(_REFLECT_CHUNK, "NVIDIA 10-K", llm, max_iterations=2)

        from app.models.graph_fact import RelationType
        assert len(facts) == 1
        assert facts[0].relation == RelationType.HAS_PRODUCT

    @pytest.mark.asyncio
    async def test_max_iterations_stops_loop(self):
        """修正始终无法通过时，达到最大轮次即停并做终局兜底过滤。"""
        from app.services.graph.reflection_graph import extract_facts_with_reflection

        bad = json.dumps({"facts": [{
            "source_entity": {"name": "NVIDIA", "type": "Company"},
            "relation": "STILL_BAD",
            "target_entity": {"name": "H100", "type": "Product"},
            "evidence": "strong demand for its H100 GPU",
            "confidence": 0.9,
        }]})
        critic_resp = json.dumps({"approve": False, "issues": ["still bad"], "missing": []})

        llm = self._role_llm(bad, critic_resp, bad)
        facts = await extract_facts_with_reflection(_REFLECT_CHUNK, "NVIDIA 10-K", llm, max_iterations=1)

        # 始终非法 → 终局过滤后为空，且不会死循环
        assert facts == []
        # 抽取1 + 评审1 + 修正1 + 评审1 = 4 次调用（max_iterations=1）
        assert llm.ainvoke.await_count == 4

    @pytest.mark.asyncio
    async def test_pipeline_reflection_mode(self, test_engine):
        """流水线在 reflection 模式下调用反思抽取并入库。"""
        from app.models.graph_source import DocumentStatus, DocumentType, SourceDocument
        from app.services.graph.pipeline import run_ingest_pipeline

        doc = SourceDocument(
            url="text://reflect-mode",
            document_type=DocumentType.EARNINGS_CALL,
            ticker="NVDA",
            company_name="NVIDIA",
            title="Reflect Mode Test",
        )
        with Session(test_engine) as s:
            s.add(doc)
            s.commit()
            s.refresh(doc)

        extract_resp = _MOCK_LLM_RESPONSE
        critic_resp = json.dumps({"approve": True, "issues": [], "missing": []})
        llm = self._role_llm(extract_resp, critic_resp, "{}")

        with (
            patch("app.services.graph.pipeline.sync_engine", test_engine),
            patch("app.services.graph.pipeline.settings.GRAPH_EXTRACTION_MODE", "reflection"),
            patch("app.services.graph.pipeline.settings.GRAPH_REFLECTION_MAX_ITERS", 1),
        ):
            count = await run_ingest_pipeline(doc, llm, raw_text=_SAMPLE_TRANSCRIPT)

        assert count > 0
        with Session(test_engine) as s:
            updated = s.get(SourceDocument, doc.id)
        assert updated.status == DocumentStatus.DONE


class TestTickerFocus:
    def test_ticker_returns_2hop_neighborhood(self):
        from app.models.graph_entity import EntityType, GraphEntity
        from app.models.graph_fact import GraphFact, RelationType
        from app.schemas.supply_chain import GraphQueryParams
        from app.services.graph.query import get_graph_data

        with _isolated_session() as s:
            nv = GraphEntity(entity_type=EntityType.COMPANY, name="NVIDIA", ticker="NVDA")
            prod = GraphEntity(entity_type=EntityType.PRODUCT, name="H100")
            supplier = GraphEntity(entity_type=EntityType.COMPANY, name="TSMC", ticker="TSM")
            unrelated = GraphEntity(entity_type=EntityType.COMPANY, name="Unrelated", ticker="ZZZZ")
            s.add_all([nv, prod, supplier, unrelated])
            s.commit()
            for e in (nv, prod, supplier, unrelated):
                s.refresh(e)

            s.add_all([
                GraphFact(source_entity_id=nv.id, target_entity_id=prod.id, relation_type=RelationType.HAS_PRODUCT,
                          evidence_text="x", confidence=0.9),
                GraphFact(source_entity_id=prod.id, target_entity_id=supplier.id, relation_type=RelationType.SUPPLIED_BY,
                          evidence_text="y", confidence=0.9),
            ])
            s.commit()

            data = get_graph_data(s, GraphQueryParams(ticker="NVDA", limit=50))
            names = {n.name for n in data.nodes}
            assert "NVIDIA" in names       # 聚焦公司
            assert "H100" in names          # 1 跳
            assert "TSMC" in names          # 2 跳
            assert "Unrelated" not in names  # 无关实体排除
