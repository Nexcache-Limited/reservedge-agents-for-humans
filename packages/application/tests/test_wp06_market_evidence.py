from __future__ import annotations

from wp06_fakes import build_facade, intent_id, jfk_payload

from itaa_application.session_models import MarketLabel, MarketSourceType


def test_market_evidence_is_synthetic_and_buyer_only() -> None:
    facade = build_facade()
    snapshot = facade.create_purchase_intent(jfk_payload())
    assert snapshot.market_evidence
    for item in snapshot.market_evidence:
        assert item.source_type is MarketSourceType.SYNTHETIC_LOCAL_FIXTURE
        assert item.label in {MarketLabel.SIMULATION, MarketLabel.LOCAL_FIXTURE}
        assert item.source_ref.startswith("market.jfk.")
        assert "http" not in item.source_ref
    stored = facade.get_buyer_snapshot(intent_id()).to_primitive()
    dumped = str(stored)
    assert "prompt" not in dumped
    assert "audit" not in dumped
    assert "buyerToken" not in dumped
