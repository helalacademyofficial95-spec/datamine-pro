"""Extraction output mapping (director, category fields) and that new extractions create queue jobs."""
import asyncio
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("bs4")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import main  # noqa: E402

ITEM = {
    "siren": "123456789", "nom_complet": "MAISON LILAS", "activite_principale": "47.11F",
    "tranche_effectif_salarie": "11",
    "siege": {"siret": "12345678900011", "numero_voie": "5", "type_voie": "PL", "libelle_voie": "DU MARCHE",
              "code_postal": "69001", "libelle_commune": "LYON"},
    "dirigeants": [{"prenoms": "Anne", "nom": "Martin"}, {"prenoms": "Anne", "nom": "Martin"}, {"denomination": "HOLDING SA"}],
}


def test_director_is_mapped_from_registry_without_inventing_names():
    record = main._directory_record(ITEM, "France")
    assert record["director"] == "Anne Martin"          # de-duplicated; legal entities are not people
    assert record["nafCode"] == "47.11F" and record["siren"] == "123456789"
    no_people = main._directory_record({**ITEM, "dirigeants": []}, "France")
    assert no_people["director"] == ""                  # stays empty -> shown as Not Found


def test_new_extraction_enqueues_each_company_once_and_starts_the_worker(monkeypatch):
    queued, started = [], []
    monkeypatch.setattr(main, "DATABASE_URL", "postgresql://x")
    monkeypatch.setattr(main.enrichment_queue, "init_table", lambda url: None)
    monkeypatch.setattr(main.enrichment_store, "load_map", lambda url: {("France", "999999999"): {}})
    monkeypatch.setattr(main.enrichment_queue, "enqueue_records", lambda url, recs: queued.extend(recs) or len(recs))

    async def fake_run(**kwargs):
        started.append(True)

    monkeypatch.setattr(main.enrichment_runner, "run_queue", fake_run)
    main.enrichment_runner.state["running"] = False
    records = [main._directory_record(ITEM, "France"),
               main._directory_record({**ITEM, "siren": "999999999"}, "France")]  # already enriched
    asyncio.run(main._auto_enrich(records))
    assert [r["siren"] for r in queued] == ["123456789"] and started == [True]
