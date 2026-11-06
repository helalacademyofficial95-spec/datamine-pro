"""Admin-token check and enrichment overlay glue (fictional companies, no network)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.enrichment import NOT_FOUND, PARTIAL, VERIFIED  # noqa: E402
from app.enrichment.service import apply_enrichment, token_ok  # noqa: E402

REC_A = {"id": "fr-100000001", "siren": "100000001", "country": "France", "name": "ALPHA SARL", "website": "",
         "b2cWebsite": None, "b2cWebsiteStatus": "no_official_website_in_registry", "director": "Jeanne Test"}
REC_B = {"id": "fr-100000002", "siren": "100000002", "country": "France", "name": "BETA SAS", "website": "",
         "b2cWebsite": None, "b2cWebsiteStatus": "no_official_website_in_registry", "director": ""}
REC_NO_ID = {"id": "x-1", "country": "France", "name": "NO NUMBER", "website": ""}


def test_token_ok_requires_configured_and_exact_token():
    assert token_ok("secret", "secret")
    assert not token_ok("secret ", "secret")
    assert not token_ok("", "secret")
    assert not token_ok(None, "secret")
    assert not token_ok("anything", "")  # no token configured -> never authorised
    assert not token_ok(None, "")


def test_apply_enrichment_overlays_only_matching_records_and_keeps_originals():
    data = {
        "officialWebsite": "https://alpha.test", "officialWebsiteStatus": VERIFIED,
        "b2cWebsite": "https://alpha.test/boutique", "b2cStatus": PARTIAL,
    }
    out = apply_enrichment([REC_A, REC_B, REC_NO_ID], lambda: {("France", "100000001"): data})
    assert out[0]["website"] == "https://alpha.test"
    assert out[0]["b2cWebsite"] == "https://alpha.test/boutique"
    assert out[0]["b2cWebsiteStatus"] == "partially_verified"
    assert out[0]["director"] == "Jeanne Test"  # registry data is never overwritten
    assert out[1] == REC_B  # not enriched yet -> untouched, legacy status preserved
    assert out[2] == REC_NO_ID
    assert REC_A["website"] == "" and "enrichment" not in REC_A  # input not mutated


def test_apply_enrichment_not_found_result_is_recorded_not_invented():
    out = apply_enrichment([REC_A], lambda: {("France", "100000001"): {"b2cStatus": NOT_FOUND, "officialWebsiteStatus": NOT_FOUND}})
    assert out[0]["website"] == "" and out[0]["b2cWebsite"] is None
    assert out[0]["b2cWebsiteStatus"] == "not_found"


def test_apply_enrichment_storage_failure_returns_plain_records():
    def broken():
        raise RuntimeError("database unavailable")

    records = [REC_A, REC_B]
    assert apply_enrichment(records, broken) == records
