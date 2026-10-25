"""プリセット軌道の定義と可動範囲検査。

docs/preset-and-schema-design.md に対応する。
各プリセットは「開始=ニュートラル → 動作waypoint → ニュートラルへ復帰」で閉じる。
関節名は実機確認済み（crane_plus_control/config/crane_plus_controllers.yaml）:
  arm:     crane_plus_joint1, crane_plus_joint2, crane_plus_joint3, crane_plus_joint4
  gripper: crane_plus_joint_hand
JointTrajectory.joint_names には上記の順序で指定する。

6プリセット（2026-10-13 Gazebo目視で関節の役割分担を確定。各関節の軸を分けて見分けられるように）:
  bow        joint2 前傾（お辞儀。挨拶・感謝）
  nod        joint2 小刻み・浅く速い（うなずき。同意。bowと深さ/速さで区別）
  cheer      joint3 跳ね上げ（腕を上げる。喜び・歓喜。一番ダイナミック）
  wave       joint4 左右（手を振る。挨拶・別れ）
  rotate_base joint1 旋回＋肘を少し曲げて向きを見せる（注目・振り向く）
  grip       joint_hand 開閉（グリッパぱくぱく。受け取る・呼応）※gripperコントローラ宛て

このモジュールは ROS 2 に依存しない（純粋データ＋検査。単体テスト可能）。
"""

from __future__ import annotations

from dataclasses import dataclass

# --- 実機確定の関節名（順序込み） --------------------------------------------------
ARM_JOINTS: tuple[str, ...] = (
    "crane_plus_joint1",
    "crane_plus_joint2",
    "crane_plus_joint3",
    "crane_plus_joint4",
)
GRIPPER_JOINTS: tuple[str, ...] = ("crane_plus_joint_hand",)

# --- 可動範囲（0中心rad。公式URDF根拠。docs/preset-and-schema-design.md 1節） -------
ARM_LIMITS: dict[str, tuple[float, float]] = {
    "crane_plus_joint1": (-2.618, 2.618),
    "crane_plus_joint2": (-1.833, 1.798),
    "crane_plus_joint3": (-2.566, 2.461),
    "crane_plus_joint4": (-1.850, 1.780),
}
GRIPPER_LIMITS: dict[str, tuple[float, float]] = {
    "crane_plus_joint_hand": (-0.716, 0.681),
}
ALL_LIMITS = {**ARM_LIMITS, **GRIPPER_LIMITS}


@dataclass(frozen=True)
class Waypoint:
    """関節の目標位置(rad)と、直前waypointからの到達時間(s)。

    positions の長さは PresetTrajectory.joint_names と一致させる
    （armなら4要素、gripperなら1要素）。
    """

    positions: tuple[float, ...]
    time_from_prev: float


@dataclass(frozen=True)
class PresetTrajectory:
    """1プリセットぶんの軌道。arm宛てか gripper宛てかを controller で区別する。"""

    name: str
    joint_names: tuple[str, ...]
    waypoints: tuple[Waypoint, ...]
    controller: str = "arm"  # "arm" または "gripper"

    def total_time(self) -> float:
        return sum(wp.time_from_prev for wp in self.waypoints)


# --- 共通ニュートラル姿勢 ----------------------------------------------------------
NEUTRAL = (0.0, 0.0, 0.0, 0.0)       # arm 4関節
GRIPPER_NEUTRAL = (0.0,)             # gripper 1関節


class RangeError(Exception):
    """プリセットのwaypointが可動範囲外。起動または実行前に送出する。"""


def check_within_limits(traj: PresetTrajectory) -> list[str]:
    """全waypointが可動範囲内か検査する。問題点のリストを返す（空なら合格）。"""
    errors: list[str] = []
    for wi, wp in enumerate(traj.waypoints):
        if len(wp.positions) != len(traj.joint_names):
            errors.append(
                f"{traj.name} waypoint[{wi}]: 位置数({len(wp.positions)})が"
                f"関節数({len(traj.joint_names)})と不一致"
            )
            continue
        for jn, pos in zip(traj.joint_names, wp.positions):
            lo, hi = ALL_LIMITS[jn]
            if not (lo <= pos <= hi):
                errors.append(
                    f"{traj.name} waypoint[{wi}] {jn}: {pos} が範囲[{lo}, {hi}]外"
                )
    return errors


# --- rotate_base 用の固定値 --------------------------------------------------------
ROTATE_ANGLE = 1.0       # joint1。±2.618 に対し十分内側
ROTATE_ELBOW = 0.6       # joint3 を少し曲げて旋回を見えるようにする（棒のままだと回転が見えない）


# --- bow（お辞儀）: joint2 前傾 ----------------------------------------------------
def build_bow(repetitions: int = 1) -> PresetTrajectory:
    """肩(joint2)を前傾させてお辞儀し、戻す（挨拶・感謝）。+0.4で見栄えするお辞儀。"""
    forward = (0.0, 0.4, 0.0, 0.0)
    wps: list[Waypoint] = [Waypoint(NEUTRAL, 0.0)]
    for _ in range(repetitions):
        wps.append(Waypoint(forward, 2.0))
        wps.append(Waypoint(forward, 0.5))
        wps.append(Waypoint(NEUTRAL, 2.0))
    return PresetTrajectory("bow", ARM_JOINTS, tuple(wps))


# --- nod（うなずく）: joint2 浅く速く ---------------------------------------------
def build_nod(repetitions: int = 1) -> PresetTrajectory:
    """肩(joint2)を浅く(+0.2)速く(0.5s)動かすうなずき（同意。bowと深さ・速さで区別）。"""
    down = (0.0, 0.2, 0.0, 0.0)
    wps: list[Waypoint] = [Waypoint(NEUTRAL, 0.0)]
    for _ in range(repetitions):
        wps.append(Waypoint(down, 0.5))
        wps.append(Waypoint(NEUTRAL, 0.5))
    return PresetTrajectory("nod", ARM_JOINTS, tuple(wps))


# --- cheer（喜び・万歳）: joint3 跳ね上げ ------------------------------------------
def build_cheer(repetitions: int = 1) -> PresetTrajectory:
    """肘(joint3)を大きく折って先端を跳ね上げる（喜び・歓喜。一番ダイナミック）。"""
    up = (0.0, 0.0, 0.8, 0.0)
    wps: list[Waypoint] = [Waypoint(NEUTRAL, 0.0)]
    for _ in range(repetitions):
        wps.append(Waypoint(up, 1.0))       # 跳ね上げ
        wps.append(Waypoint(up, 0.3))       # 保持
        wps.append(Waypoint(NEUTRAL, 1.0))  # 戻す
    return PresetTrajectory("cheer", ARM_JOINTS, tuple(wps))


# --- wave（手を振る）: joint4 左右 -------------------------------------------------
def build_wave(repetitions: int = 1) -> PresetTrajectory:
    """肘(joint3)を少し曲げて先端を上げ、手首(joint4)を左右に振る（挨拶・別れ）。"""
    ready = (0.0, 0.0, 0.5, 0.0)       # 肘を少し曲げて先端を立てる
    swing_p = (0.0, 0.0, 0.5, 0.5)
    swing_m = (0.0, 0.0, 0.5, -0.5)
    wps: list[Waypoint] = [Waypoint(NEUTRAL, 0.0), Waypoint(ready, 1.0)]
    for _ in range(repetitions):
        wps.append(Waypoint(swing_p, 0.5))
        wps.append(Waypoint(swing_m, 0.5))
    wps.append(Waypoint(NEUTRAL, 1.0))
    return PresetTrajectory("wave", ARM_JOINTS, tuple(wps))


# --- rotate_base（左右を向く）: joint1 旋回＋肘を添える ----------------------------
def build_rotate_base(direction: str) -> PresetTrajectory:
    """肘(joint3)を少し曲げた姿勢で基部(joint1)を回し、向きの変化を見せる。

    角度はLLMから受け取らず direction(left/right) で符号だけ決める。
    棒のまま回すと回転が見えないため joint3 を添えて先端を振らせる。
    """
    sign = 1.0 if direction == "left" else -1.0
    posed = (0.0, 0.0, ROTATE_ELBOW, 0.0)                 # 肘を曲げた基本姿勢
    turned = (sign * ROTATE_ANGLE, 0.0, ROTATE_ELBOW, 0.0)  # その姿勢で旋回
    wps = (
        Waypoint(NEUTRAL, 0.0),
        Waypoint(posed, 1.0),    # 肘を曲げる
        Waypoint(turned, 1.5),   # 旋回
        Waypoint(turned, 0.5),   # 保持
        Waypoint(posed, 1.5),    # 正面へ戻す
        Waypoint(NEUTRAL, 1.0),  # ニュートラルへ
    )
    return PresetTrajectory("rotate_base", ARM_JOINTS, wps)


# --- grip（グリッパ開閉）: gripper コントローラ宛て --------------------------------
def build_grip(repetitions: int = 1) -> PresetTrajectory:
    """グリッパ(joint_hand)を開閉する（受け取る・呼応。パクパク）。

    gripperコントローラ宛て（armとは別トピック）。開=+0.5 / 閉=-0.3。
    """
    open_p = (0.5,)
    close_p = (-0.3,)
    wps: list[Waypoint] = [Waypoint(GRIPPER_NEUTRAL, 0.0)]
    for _ in range(repetitions):
        wps.append(Waypoint(open_p, 0.6))    # 開く
        wps.append(Waypoint(close_p, 0.6))   # 閉じる
    wps.append(Waypoint(GRIPPER_NEUTRAL, 0.6))  # 中立へ
    return PresetTrajectory("grip", GRIPPER_JOINTS, tuple(wps), controller="gripper")


def startup_range_check() -> None:
    """起動時の自己検査。全プリセットの代表軌道が可動範囲内か確かめる。"""
    errors: list[str] = []
    errors += check_within_limits(build_bow(repetitions=5))
    errors += check_within_limits(build_nod(repetitions=5))
    errors += check_within_limits(build_cheer(repetitions=5))
    errors += check_within_limits(build_wave(repetitions=5))
    errors += check_within_limits(build_rotate_base("left"))
    errors += check_within_limits(build_rotate_base("right"))
    errors += check_within_limits(build_grip(repetitions=5))
    if errors:
        raise RangeError("; ".join(errors))
