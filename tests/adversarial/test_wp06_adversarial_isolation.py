from __future__ import annotations

from wp04_helpers import A1_ID, A2_ID, SUPPLIERS  # type: ignore[import-not-found]
from wp06_fakes import (  # type: ignore[import-not-found]
    FixtureRoster,
    build_facade,
    governance,
    intent_id,
    jfk_payload,
)


def test_one_supplier_never_sees_another_token() -> None:
    roster = FixtureRoster()
    facade = build_facade(roster=roster)
    facade.create_purchase_intent(jfk_payload())
    facade.confirm_requirement(intent_id(), governance(A1_ID))
    facade.approve_and_dispatch(intent_id(), governance(A2_ID))
    seen = {
        token.to_primitive(): list(port.seen_envelopes) for token, port in roster.ports().items()
    }
    for token, envelopes in seen.items():
        assert envelopes
        dumped = str(envelopes)
        for other in SUPPLIERS:
            if other.to_primitive() == token:
                continue
            assert other.to_primitive() not in dumped
        assert "competitor" not in dumped
        assert "recipientCount" not in dumped
