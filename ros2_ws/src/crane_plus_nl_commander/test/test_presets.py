"""presets.py の単体テスト（ROS 非依存）。

docs/preset-and-schema-design.md 1〜2節の軌道設計と可動範囲検査を検査する。
"""

from crane_plus_nl_commander.presets import (
    ARM_JOINTS,
    ARM_LIMITS,
    GRIPPER_NEUTRAL,
    NEUTRAL,
    PresetTrajectory,
    Waypoint,
    build_bow,
    build_cheer,
    build_grip,
    build_nod,
    build_rotate_base,
    build_wave,
    check_within_limits,
    startup_range_check,
)


def test_arm_joint_names_order():
    # 実機確認済みのプレフィックス付き名・順序
    assert ARM_JOINTS == (
        "crane_plus_joint1",
        "crane_plus_joint2",
        "crane_plus_joint3",
        "crane_plus_joint4",
    )


def test_bow_starts_and_ends_neutral():
    traj = build_bow(repetitions=1)
    assert traj.waypoints[0].positions == (0.0, 0.0, 0.0, 0.0)
    assert traj.waypoints[-1].positions == (0.0, 0.0, 0.0, 0.0)


def test_bow_within_limits():
    assert check_within_limits(build_bow(repetitions=1)) == []
    assert check_within_limits(build_bow(repetitions=3)) == []


def test_bow_repetitions_add_waypoints():
    # 1回 = 開始 + (前傾,保持,復帰)=3 → 4点。3回 = 開始 + 3*3 = 10点。
    assert len(build_bow(repetitions=1).waypoints) == 4
    assert len(build_bow(repetitions=3).waypoints) == 10


def test_out_of_range_detected():
    bad = PresetTrajectory(
        name="bad",
        joint_names=ARM_JOINTS,
        waypoints=(Waypoint((99.0, 0.0, 0.0, 0.0), 1.0),),
    )
    errors = check_within_limits(bad)
    assert len(errors) == 1
    assert "crane_plus_joint1" in errors[0]


def test_limits_cover_all_arm_joints():
    assert set(ARM_LIMITS.keys()) == set(ARM_JOINTS)


def test_arm_presets_start_end_neutral():
    # arm系プリセットは開始・終了がニュートラル
    for build in (build_bow, build_nod, build_cheer, build_wave):
        traj = build(repetitions=2)
        assert traj.waypoints[0].positions == NEUTRAL
        assert traj.waypoints[-1].positions == NEUTRAL


def test_grip_start_end_gripper_neutral():
    traj = build_grip(repetitions=2)
    assert traj.controller == "gripper"
    assert traj.waypoints[0].positions == GRIPPER_NEUTRAL
    assert traj.waypoints[-1].positions == GRIPPER_NEUTRAL


def test_all_presets_within_limits():
    for build in (build_bow, build_nod, build_cheer, build_wave, build_grip):
        for reps in (1, 5):
            assert check_within_limits(build(repetitions=reps)) == []
    for d in ("left", "right"):
        assert check_within_limits(build_rotate_base(d)) == []


def test_rotate_base_direction_sign():
    # left は joint1 正方向、right は負方向。旋回後の最大|joint1|で判定（waypoint構造に依存しない）
    left_j1 = [wp.positions[0] for wp in build_rotate_base("left").waypoints]
    right_j1 = [wp.positions[0] for wp in build_rotate_base("right").waypoints]
    assert max(left_j1) > 0 and min(left_j1) >= 0      # left は正方向のみ
    assert min(right_j1) < 0 and max(right_j1) <= 0    # right は負方向のみ


def test_rotate_base_start_end_neutral():
    traj = build_rotate_base("left")
    assert traj.waypoints[0].positions == NEUTRAL
    assert traj.waypoints[-1].positions == NEUTRAL


def test_nod_uses_only_joint2():
    # nod は joint1/3/4 を動かさない（joint2のみ）
    for wp in build_nod(repetitions=3).waypoints:
        assert wp.positions[0] == 0.0  # joint1
        assert wp.positions[2] == 0.0  # joint3
        assert wp.positions[3] == 0.0  # joint4


def test_startup_range_check_passes():
    # 例外が出なければ合格
    startup_range_check()
