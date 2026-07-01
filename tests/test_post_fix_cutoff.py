"""POST_FIX_CUTOFF must be the actual moment every fix commit landed
(20:43-21:02 UTC on 2026-07-01), not the earlier 20:00:00 that let pre-fix
edges leak into the "post-fix" record."""

from engine.config import POST_FIX_CUTOFF


def test_post_fix_cutoff_is_after_last_fix_commit():
    assert POST_FIX_CUTOFF == "2026-07-01T21:05:00"


def test_build_record_report_uses_post_fix_cutoff_constant(monkeypatch):
    import engine.settlement as settlement

    seen_since: list[str | None] = []
    settled_summary = {
        "settled": 1, "wins": 1, "losses": 0, "pushes": 0, "voids": 0,
        "hit_rate": 100.0, "avg_predicted_prob": None, "by_verdict": {},
    }

    def fake_get_record_summary(since=None):
        seen_since.append(since)
        return settled_summary

    monkeypatch.setattr(settlement, "get_record_summary", fake_get_record_summary)
    settlement.build_record_report()

    assert POST_FIX_CUTOFF in seen_since
