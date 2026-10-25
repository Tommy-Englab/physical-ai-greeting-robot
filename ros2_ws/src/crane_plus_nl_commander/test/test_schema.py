"""schema.py の単体テスト（ROS 非依存）。

design.md 3.4 の検証順序と docs/preset-and-schema-design.md 3.2 の上限を検査する。
"""

import pytest

from crane_plus_nl_commander.schema import (
    MAX_RESPONSE_BYTES,
    Plan,
    Preset,
    ValidationFailure,
    to_canonical_json,
    validate_response,
)


def test_valid_bow():
    raw = '{"version":"1.0","actions":[{"preset":"bow","parameters":{"repetitions":1}}]}'
    plan = validate_response(raw)
    assert isinstance(plan, Plan)
    assert plan.actions[0].preset == Preset.bow
    assert plan.actions[0].parameters.repetitions == 1


def test_valid_compound_order():
    raw = (
        '{"version":"1.0","actions":['
        '{"preset":"rotate_base","parameters":{"direction":"right"}},'
        '{"preset":"bow","parameters":{"repetitions":1}}]}'
    )
    plan = validate_response(raw)
    assert [a.preset for a in plan.actions] == [Preset.rotate_base, Preset.bow]


def test_unknown_preset_rejected():
    raw = '{"version":"1.0","actions":[{"preset":"grab","parameters":{}}]}'
    with pytest.raises(ValidationFailure):
        validate_response(raw)


def test_unknown_field_rejected():
    # joint_angles 等の生制御値はスキーマに無いので拒否される
    raw = (
        '{"version":"1.0","actions":[{"preset":"bow",'
        '"parameters":{"joint_angles":[0.1,0.2]}}]}'
    )
    with pytest.raises(ValidationFailure):
        validate_response(raw)


def test_repetitions_within_limit_accepted():
    # 上限5なので5は有効
    raw = '{"version":"1.0","actions":[{"preset":"nod","parameters":{"repetitions":5}}]}'
    plan = validate_response(raw)
    assert plan.actions[0].parameters.repetitions == 5


def test_repetitions_over_limit_rejected():
    raw = '{"version":"1.0","actions":[{"preset":"bow","parameters":{"repetitions":6}}]}'
    with pytest.raises(ValidationFailure):
        validate_response(raw)


def test_all_five_presets_accepted():
    raw = (
        '{"version":"1.0","actions":['
        '{"preset":"bow","parameters":{}},'
        '{"preset":"nod","parameters":{"repetitions":3}},'
        '{"preset":"wave","parameters":{"repetitions":2}},'
        '{"preset":"cheer","parameters":{}},'
        '{"preset":"rotate_base","parameters":{"direction":"left"}}]}'
    )
    plan = validate_response(raw)
    assert [a.preset for a in plan.actions] == [
        Preset.bow, Preset.nod, Preset.wave, Preset.cheer, Preset.rotate_base
    ]


def test_grip_accepted():
    raw = '{"version":"1.0","actions":[{"preset":"grip","parameters":{"repetitions":3}}]}'
    plan = validate_response(raw)
    assert plan.actions[0].preset == Preset.grip
    assert plan.actions[0].parameters.repetitions == 3


def test_cheer_rejects_direction():
    raw = (
        '{"version":"1.0","actions":[{"preset":"cheer",'
        '"parameters":{"direction":"left"}}]}'
    )
    with pytest.raises(ValidationFailure):
        validate_response(raw)


def test_too_many_actions_rejected():
    actions = ",".join(['{"preset":"bow","parameters":{}}'] * 6)
    raw = '{"version":"1.0","actions":[' + actions + "]}"
    with pytest.raises(ValidationFailure):
        validate_response(raw)


def test_rotate_base_requires_direction():
    raw = '{"version":"1.0","actions":[{"preset":"rotate_base","parameters":{}}]}'
    with pytest.raises(ValidationFailure):
        validate_response(raw)


def test_bow_rejects_direction():
    raw = (
        '{"version":"1.0","actions":[{"preset":"bow",'
        '"parameters":{"direction":"left"}}]}'
    )
    with pytest.raises(ValidationFailure):
        validate_response(raw)


def test_prose_mixed_in_rejected():
    raw = 'ここに計画です: {"version":"1.0","actions":[{"preset":"bow","parameters":{}}]}'
    with pytest.raises(ValidationFailure):
        validate_response(raw)


def test_oversized_response_rejected():
    raw = '{"version":"1.0","actions":[{"preset":"bow","parameters":{}}]}' + (
        " " * (MAX_RESPONSE_BYTES + 1)
    )
    with pytest.raises(ValidationFailure):
        validate_response(raw)


def test_canonical_excludes_none():
    raw = '{"version":"1.0","actions":[{"preset":"bow","parameters":{"repetitions":1}}]}'
    plan = validate_response(raw)
    canonical = to_canonical_json(plan)
    assert "direction" not in canonical  # 未指定は落ちる
    assert '"repetitions": 1' in canonical
