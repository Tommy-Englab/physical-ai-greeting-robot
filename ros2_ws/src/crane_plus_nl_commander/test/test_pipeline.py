"""LLMを差し替えたコンポーネントテスト（ROS msg は使わない）。

GeminiをフェイクのPlanGeneratorに置換し、client→validator→canonical→preset展開の
データフロー（design.md 2.1）を Gemini なしで検査する。
"""

import pytest

from crane_plus_nl_commander.presets import build_bow, check_within_limits
from crane_plus_nl_commander.schema import (
    Preset,
    ValidationFailure,
    to_canonical_json,
    validate_response,
)


class FakeGenerator:
    """固定のraw応答を返すフェイク（PlanGenerator プロトコル準拠）。"""

    def __init__(self, raw: str) -> None:
        self._raw = raw

    def generate(self, instruction: str) -> str:  # noqa: ARG002
        return self._raw


def test_fake_bow_flows_to_preset():
    gen = FakeGenerator(
        '{"version":"1.0","actions":[{"preset":"bow","parameters":{"repetitions":2}}]}'
    )
    raw = gen.generate("お辞儀して2回")
    plan = validate_response(raw)

    # canonical 表示が作れる
    assert "bow" in to_canonical_json(plan)

    # bow preset へ展開でき、可動範囲内
    action = plan.actions[0]
    assert action.preset == Preset.bow
    traj = build_bow(repetitions=action.parameters.repetitions)
    assert check_within_limits(traj) == []


def test_fake_invalid_output_stops_before_preset():
    # 生の関節角を混ぜた不正出力 → 検証で停止し、preset展開に到達しない
    gen = FakeGenerator(
        '{"version":"1.0","actions":[{"preset":"bow",'
        '"parameters":{"joint_angles":[0.1]}}]}'
    )
    with pytest.raises(ValidationFailure):
        validate_response(gen.generate("悪意ある指示"))
