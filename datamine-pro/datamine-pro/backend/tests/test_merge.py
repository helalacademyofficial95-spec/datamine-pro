"""Overlay and batch-selection tests (pure logic, fictional records)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.enrichment import NOT_FOUND, PARTIAL, UNVERIFIED, VERIFIED  # noqa: E402
from app.enrichment.merge import overlay_enrichment, record_key, select_pending  # noqa: E402

REC = {"id": "fr-123456789", "siren": "123456789", "country": "France", "name": "X",
       "website": "", "b2cWebsite": None, "verification": "Unverified", "director": "A B"}


def test_record_key_requires_registration_number_and_country():
    assert record_key(REC) == ("France", "123456789")
    assert record_key({"siren": "", "country": "France"}) is None
    assert record_key({"siren": "123456789", "country": ""}) is None
    assert record_key({"sourceRecordId": "0123.456.789", "country": "Belgium"}) == ("Belgium", "0123456789")


def test_overlay_never_mutates_input_and_keeps_other_fields():
    data = {"officialWebsite": "https://x.fr", "officialWebsiteStatus": VERIFIED,
            "b2cWebsite": "https://x.fr", "b2cStatus": VERIFIED}
    out = overlay_enrichment(REC, data)
    assert REC["website"] == "" and "enrichment" not in REC
    assert out["website"] == "https://x.fr" and out["director"] == "A B"
    assert out["verification"] == "Verified" and out["b2cWebsiteStatus"] == "verified"


def test_overlay_partial_maps_to_partially_verified():
    out = overlay_enrichment(REC, {"officialWebsite": "https://x.fr", "officialWebsiteStatus": PARTIAL,
                                   "b2cWebsite": "https://x.fr", "b2cStatus": PARTIAL})
    assert out["verification"] == "Partially verified" and out["b2cWebsite"] == "https://x.fr"


def test_unverified_candidates_never_become_visible_websites():
    data = {"officialWebsite": None, "officialWebsiteStatus": UNVERIFIED, "officialWebsiteCandidate": "https://maybe.fr",
            "b2cWebsite": None, "b2cCandidateUrl": "https://maybe.fr", "b2cStatus": UNVERIFIED}
    out = overlay_enrichment(REC, data)
    assert out["website"] == "" and out["b2cWebsite"] is None
    assert out["b2cWebsiteStatus"] == "unverified" and out["verification"] == "Unverified"
    assert out["enrichment"]["b2cCandidateUrl"] == "https://maybe.fr"  # audit trail kept


def test_unverified_b2c_url_is_dropped_even_if_present_in_data():
    out = overlay_enrichment(REC, {"b2cWebsite": "https://maybe.fr", "b2cStatus": UNVERIFIED})
    assert out["b2cWebsite"] is None


def test_no_enrichment_returns_plain_copy():
    out = overlay_enrichment(REC, None)
    assert out == REC and out is not REC


def test_not_found_status_slug():
    assert overlay_enrichment(REC, {"b2cStatus": NOT_FOUND})["b2cWebsiteStatus"] == "not_found"


def test_select_pending_skips_done_dedupes_and_respects_limit():
    records = [{**REC, "siren": f"10000000{i}"} for i in range(6)] + [{**REC, "siren": "100000000"}]
    done = {("France", "100000001"), ("France", "100000002")}
    pending = select_pending(records, done, limit=3)
    assert [r["siren"] for r in pending] == ["100000000", "100000003", "100000004"]
    assert len(select_pending(records, done, limit=50, force=True)) == 6
    assert select_pending([{"siren": "", "country": "France"}], set(), 5) == []
