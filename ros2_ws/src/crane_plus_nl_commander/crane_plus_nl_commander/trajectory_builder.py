"""検証済みプリセット軌道を trajectory_msgs/msg/JointTrajectory へ変換する。

design.md 3.2 の Trajectory publisher の変換部分。送信は nl_commander ノードが行う。
PresetTrajectory の time_from_prev を積算して各 point の time_from_start を作る。
"""

from __future__ import annotations

from builtin_interfaces.msg import Duration
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint

from .presets import PresetTrajectory


def _to_duration(seconds: float) -> Duration:
    sec = int(seconds)
    nanosec = int(round((seconds - sec) * 1e9))
    return Duration(sec=sec, nanosec=nanosec)


def build_joint_trajectory(traj: PresetTrajectory) -> JointTrajectory:
    """PresetTrajectory を JointTrajectory メッセージへ変換する。

    最初の waypoint（開始ニュートラル, time_from_prev=0）も含め、
    time_from_start は先頭からの積算時間にする。
    """
    msg = JointTrajectory()
    msg.joint_names = list(traj.joint_names)

    elapsed = 0.0
    for wp in traj.waypoints:
        elapsed += wp.time_from_prev
        point = JointTrajectoryPoint()
        point.positions = list(wp.positions)
        point.time_from_start = _to_duration(elapsed)
        msg.points.append(point)

    return msg
