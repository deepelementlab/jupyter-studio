from __future__ import annotations

from clawcode.learning.quality_gates import evaluate_evolved_skill_quality


def test_evolved_skill_quality_gate_detects_invalid(tmp_path) -> None:
    d = tmp_path / "skills" / "a"
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text("no title\n", encoding="utf-8")
    out = evaluate_evolved_skill_quality(tmp_path / "skills")
    assert out["ok"] is False
    assert out["short_circuit_import"] is True

