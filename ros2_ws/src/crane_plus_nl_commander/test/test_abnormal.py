"""異常系の網羅テスト（Task 4 加点枠・AC-4。ROS/Gemini 非依存）。

LLMがこう返したらどうなるか、を fixture で検証する。live を一切消費しない。
不正系では ValidationFailure（＝ロボットへ送らない）になることを確認する。
"""

import pytest

from crane_plus_nl_commander.schema import (
    MAX_RESPONSE_BYTES,
    ValidationFailure,
    validate_response,
)

# ロボットへ送ってはいけない（検証で止まるべき）異常系 fixture
REJECT_CASES = {
    "空文字": "",
    "非JSON": "これは計画ではありません",
    "説明文混入": 'はい計画です {"version":"1.0","actions":[{"preset":"bow","parameters":{}}]}',
    "markdown_fence": (
        '```json\n{"version":"1.0","actions":[{"preset":"bow","parameters":{}}]}\n```'
    ),
    "version欠落": '{"actions":[{"preset":"bow","parameters":{}}]}',
    "version不正": '{"version":"2.0","actions":[{"preset":"bow","parameters":{}}]}',
    "actions空": '{"version":"1.0","actions":[]}',
    "actions欠落": '{"version":"1.0"}',
    "未知preset": '{"version":"1.0","actions":[{"preset":"grab","parameters":{}}]}',
    "未知field_生制御値": (
        '{"version":"1.0","actions":[{"preset":"bow",'
        '"parameters":{"joint_angles":[0.1,0.2,0.3,0.4]}}]}'
    ),
    "未知field_速度": (
        '{"version":"1.0","actions":[{"preset":"bow",'
        '"parameters":{"velocity":2.0}}]}'
    ),
    "トップレベル未知field": (
        '{"version":"1.0","topic":"/cmd","actions":[{"preset":"bow","parameters":{}}]}'
    ),
    "型不正_repetitions文字列": (
        '{"version":"1.0","actions":[{"preset":"bow","parameters":{"repetitions":"three"}}]}'
    ),
    "回数超過": '{"version":"1.0","actions":[{"preset":"bow","parameters":{"repetitions":6}}]}',
    "回数ゼロ": '{"version":"1.0","actions":[{"preset":"bow","parameters":{"repetitions":0}}]}',
    "action数超過": (
        '{"version":"1.0","actions":['
        + ",".join(['{"preset":"bow","parameters":{}}'] * 6)
        + "]}"
    ),
    "rotate方向欠落": '{"version":"1.0","actions":[{"preset":"rotate_base","parameters":{}}]}',
    "rotate方向不正": (
        '{"version":"1.0","actions":[{"preset":"rotate_base","parameters":{"direction":"up"}}]}'
    ),
    "rotateにrepetitions": (
        '{"version":"1.0","actions":[{"preset":"rotate_base",'
        '"parameters":{"direction":"left","repetitions":2}}]}'
    ),
    "bowにdirection": (
        '{"version":"1.0","actions":[{"preset":"bow","parameters":{"direction":"left"}}]}'
    ),
}


@pytest.mark.parametrize("name,raw", list(REJECT_CASES.items()))
def test_abnormal_rejected(name, raw):
    with pytest.raises(ValidationFailure):
        validate_response(raw)


def test_oversized_rejected():
    raw = (
        '{"version":"1.0","actions":[{"preset":"bow","parameters":{}}]}'
        + " " * (MAX_RESPONSE_BYTES + 1)
    )
    with pytest.raises(ValidationFailure):
        validate_response(raw)


def test_plan_time_over_limit_rejected():
    # 見積時間が上限を超える計画は、見積関数を注入すると拒否される。
    # ダミーの見積関数で 46s を返させる（上限45s）。
    raw = '{"version":"1.0","actions":[{"preset":"bow","parameters":{"repetitions":1}}]}'
    with pytest.raises(ValidationFailure):
        validate_response(raw, estimate_seconds=lambda plan: 46.0)


def test_plan_time_within_limit_ok():
    raw = '{"version":"1.0","actions":[{"preset":"bow","parameters":{"repetitions":1}}]}'
    plan = validate_response(raw, estimate_seconds=lambda plan: 10.0)
    assert plan.actions[0].preset.value == "bow"
