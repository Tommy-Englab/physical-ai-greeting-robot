"""見積時間とプリセット展開のテスト（nl_commander のモジュール関数）。

nl_commander は rclpy を import するため、コンテナ内（ROS 2 環境）で実行する。
"""

from crane_plus_nl_commander.nl_commander import (
    _action_to_trajectory,
    estimate_plan_seconds,
)
from crane_plus_nl_commander.schema import validate_response


def test_estimate_single_bow():
    plan = validate_response(
        '{"version":"1.0","actions":[{"preset":"bow","parameters":{"repetitions":1}}]}'
    )
    assert abs(estimate_plan_seconds(plan) - 4.5) < 0.01


def test_estimate_compound_matches_sum():
    plan = validate_response(
        '{"version":"1.0","actions":['
        '{"preset":"rotate_base","parameters":{"direction":"left"}},'
        '{"preset":"wave","parameters":{"repetitions":2}}]}'
    )
    # rotate 5.5 + wave(r2) 4.0 = 9.5
    assert abs(estimate_plan_seconds(plan) - 9.5) < 0.01


def test_action_to_trajectory_all_presets():
    plan = validate_response(
        '{"version":"1.0","actions":['
        '{"preset":"bow","parameters":{}},'
        '{"preset":"nod","parameters":{"repetitions":2}},'
        '{"preset":"wave","parameters":{"repetitions":1}},'
        '{"preset":"cheer","parameters":{}},'
        '{"preset":"rotate_base","parameters":{"direction":"right"}}]}'
    )
    names = [_action_to_trajectory(a).name for a in plan.actions]
    assert names == ["bow", "nod", "wave", "cheer", "rotate_base"]
