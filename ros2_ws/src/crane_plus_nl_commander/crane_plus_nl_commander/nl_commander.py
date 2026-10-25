"""CRANE+ V2 自然言語コマンダ（ノード本体）。

テーマ: あいさつコミュニケーションロボット（requirements 1.1）。
データフロー（design.md 2.1）:
  自然言語 → LLM client → validator(schema+意味+見積時間) → canonical JSON表示
          → presetへ展開 → 可動範囲検査 → JointTrajectory → publish

6プリセット（bow/nod/cheer/wave/rotate_base/grip）。あいさつ語・感情も解釈する。
検証不合格・未対応・範囲外では JointTrajectory を一切 publish しない（安全停止）。

モード（AC-6）:
  live  : Gemini に推論させる（既定）。成功した canonical JSON は --save で保存できる。
  saved : 保存済み canonical JSON を同じ validator に通して再生する（LLMを呼ばない）。
  API障害時に自動で saved へ切り替えない。モードは画面・ログに明記する。

使い方（コンテナ内、Gazebo起動済みのシェルで）:
  source /opt/ros/humble/setup.bash
  source ~/airobot_ws/install/setup.bash
  source /workspace/ros2_ws/install/setup.bash
  set -a; source ~/gemini.env; set +a   # GEMINI_API_KEY
  # live（任意で保存）:
  ros2 run crane_plus_nl_commander nl_commander "こんにちは" --save /workspace/plans/hello.json
  # saved 再生（RPD枯渇時の保険。live を消費しない）:
  ros2 run crane_plus_nl_commander nl_commander --saved /workspace/plans/hello.json
"""

from __future__ import annotations

import sys

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile
from trajectory_msgs.msg import JointTrajectory

from .llm_client import GeminiPlanGenerator, LLMError, PlanGenerator
from .presets import (
    PresetTrajectory,
    RangeError,
    build_bow,
    build_cheer,
    build_grip,
    build_nod,
    build_rotate_base,
    build_wave,
    check_within_limits,
    startup_range_check,
)
from .schema import Action, Plan, Preset, ValidationFailure, to_canonical_json, validate_response
from .trajectory_builder import build_joint_trajectory


def _action_to_trajectory(action: Action) -> PresetTrajectory:
    """検証済み action を対応するプリセット軌道へ展開する（モジュール関数）。"""
    reps = action.parameters.repetitions or 1
    if action.preset == Preset.bow:
        return build_bow(repetitions=reps)
    if action.preset == Preset.nod:
        return build_nod(repetitions=reps)
    if action.preset == Preset.cheer:
        return build_cheer(repetitions=reps)
    if action.preset == Preset.wave:
        return build_wave(repetitions=reps)
    if action.preset == Preset.grip:
        return build_grip(repetitions=reps)
    return build_rotate_base(action.parameters.direction.value)


def estimate_plan_seconds(plan: Plan) -> float:
    """計画全体の見積総時間(秒)。各 action の軌道 total_time を合算（validatorへ注入）。"""
    return sum(_action_to_trajectory(a).total_time() for a in plan.actions)


ARM_TRAJECTORY_TOPIC = "/crane_plus_arm_controller/joint_trajectory"
GRIPPER_TRAJECTORY_TOPIC = "/crane_plus_gripper_controller/joint_trajectory"


class NLCommander(Node):
    """自然言語1指示を受け、検証を通ったプリセットだけをGazeboへ送るノード。"""

    def __init__(self, generator: PlanGenerator | None) -> None:
        super().__init__("nl_commander")
        self._generator = generator  # saved モードでは None

        # 起動時の自己検査: 全プリセットが可動範囲内であることを確認（範囲外なら例外）。
        startup_range_check()

        qos = QoSProfile(depth=10)
        self._arm_pub = self.create_publisher(JointTrajectory, ARM_TRAJECTORY_TOPIC, qos)
        self._gripper_pub = self.create_publisher(JointTrajectory, GRIPPER_TRAJECTORY_TOPIC, qos)

    def run_live(self, instruction: str, save_path: str | None = None) -> int:
        """live モード: Gemini に推論させて実行する。任意で canonical JSON を保存する。"""
        self.get_logger().info("[MODE: live] 指示: " + instruction)

        try:
            raw = self._generator.generate(instruction)
        except LLMError as exc:
            self.get_logger().error(f"[停止] LLM失敗: {exc}（ロボットへは送らない）")
            return 1

        plan = self._validate_or_stop(raw)
        if plan is None:
            return 1

        if save_path is not None:
            self._save_plan(plan, save_path)

        return self._execute(plan)

    def run_saved(self, path: str) -> int:
        """saved モード: 保存済み canonical JSON を同じ validator に通して再生する。"""
        self.get_logger().info(f"[MODE: saved] 保存計画を再生: {path}")
        try:
            with open(path, encoding="utf-8") as f:
                raw = f.read()
        except OSError as exc:
            self.get_logger().error(f"[停止] 保存計画の読み込み失敗: {type(exc).__name__}")
            return 1

        # 保存計画も信頼せず、live と同じ検証を通す。
        plan = self._validate_or_stop(raw)
        if plan is None:
            return 1

        return self._execute(plan)

    def _validate_or_stop(self, raw: str) -> Plan | None:
        """検証（schema+意味+見積時間）。合格なら Plan、不合格なら None（ログ出力）。"""
        try:
            plan = validate_response(raw, estimate_seconds=estimate_plan_seconds)
        except ValidationFailure as exc:
            self.get_logger().error("[停止] 検証不合格（ロボットへは送らない）:")
            for r in exc.reasons:
                self.get_logger().error(f"  - {r}")
            return None
        # canonical JSON を実行前に表示（design 3.4 手順7）
        self.get_logger().info("検証合格。canonical plan:\n" + to_canonical_json(plan))
        return plan

    def _save_plan(self, plan: Plan, path: str) -> None:
        """検証済み計画を canonical JSON としてファイル保存する（saved再生用）。"""
        try:
            import os

            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(to_canonical_json(plan))
            self.get_logger().info(f"canonical plan を保存: {path}")
        except OSError as exc:
            self.get_logger().warning(f"保存に失敗（実行は継続）: {type(exc).__name__}")

    def _execute(self, plan: Plan) -> int:
        for i, action in enumerate(plan.actions):
            traj = _action_to_trajectory(action)

            # 実行直前の可動範囲検査（内部プリセットも信頼しない）
            range_errors = check_within_limits(traj)
            if range_errors:
                self.get_logger().error("[停止] 可動範囲外（送らない）:")
                for r in range_errors:
                    self.get_logger().error(f"  - {r}")
                return 1

            msg = build_joint_trajectory(traj)
            pub = self._gripper_pub if traj.controller == "gripper" else self._arm_pub
            pub.publish(msg)
            self.get_logger().info(
                f"actions[{i}] '{action.preset.value}' を送信（{traj.controller}, "
                f"{len(msg.points)}点, 総時間 {traj.total_time():.1f}s）"
            )
            # 前の動作が終わるまで待ってから次を送る（連結の順序保証）。
            self._wait(traj.total_time() + 0.5)
        return 0

    def _wait(self, seconds: float) -> None:
        """軌道の実行時間ぶん spin しながら待つ（複数動作の順序実行用）。"""
        end = self.get_clock().now().nanoseconds + int(seconds * 1e9)
        while rclpy.ok() and self.get_clock().now().nanoseconds < end:
            rclpy.spin_once(self, timeout_sec=0.1)


def _parse_args(argv: list[str]) -> tuple[str, str | None, str | None]:
    """簡易引数解析。戻り値 = (instruction, save_path, saved_path)。

    - `--saved <file>`: saved モード（再生）。instruction は不要。
    - `--save <file>` : live モードで成功した計画を保存。
    - それ以外の語     : instruction（自然言語指示）として連結。
    """
    instruction_parts: list[str] = []
    save_path: str | None = None
    saved_path: str | None = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--saved" and i + 1 < len(argv):
            saved_path = argv[i + 1]
            i += 2
        elif a == "--save" and i + 1 < len(argv):
            save_path = argv[i + 1]
            i += 2
        else:
            instruction_parts.append(a)
            i += 1
    instruction = " ".join(instruction_parts).strip()
    return instruction, save_path, saved_path


def main() -> None:
    instruction, save_path, saved_path = _parse_args(sys.argv[1:])

    rclpy.init()
    exit_code = 0
    node: NLCommander | None = None
    try:
        if saved_path is not None:
            # saved モードは LLM を使わない（キー不要・RPD消費ゼロ）。
            node = NLCommander(generator=None)
        else:
            generator = GeminiPlanGenerator()
            node = NLCommander(generator)
    except (LLMError, RangeError) as exc:
        print(f"[起動失敗] {exc}", file=sys.stderr)
        rclpy.shutdown()
        raise SystemExit(2)

    try:
        if saved_path is not None:
            exit_code = node.run_saved(saved_path)
        else:
            exit_code = node.run_live(instruction or "お辞儀して", save_path=save_path)
    finally:
        node.destroy_node()
        rclpy.shutdown()

    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
