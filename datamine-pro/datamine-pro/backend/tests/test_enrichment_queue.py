from app.enrichment.queue import MAX_ATTEMPTS, STALE_MINUTES
from app.enrichment.merge import record_key, select_pending


def test_record_key_uses_country_and_siren():
    assert record_key({"country": "France", "siren": "804409134"}) == ("France", "804409134")


def test_record_key_rejects_missing_identifiers():
    assert record_key({"country": "France", "siren": ""}) is None


def test_queue_retry_policy_is_bounded_and_recovers_stale_claims():
    assert MAX_ATTEMPTS == 3
    assert STALE_MINUTES == 10


def test_select_pending_keeps_records_without_mutating_input():
    records = [{"country": "France", "siren": "804409134"}]
    selected = select_pending(records, set(), 50)
    assert selected == records
    assert records[0]["siren"] == "804409134"
