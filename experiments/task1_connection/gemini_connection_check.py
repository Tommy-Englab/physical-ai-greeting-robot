"""Task 1 接続・最小推論ゲート用の最小スクリプト。

目的（撤退判断ゲート。design 3.5 / tasks Task 1 に対応）:
  1. コンテナから Gemini の公式HTTPS endpoint へ接続できるか。
  2. 最小のテキスト推論が1回成功するか（status・所要時間を記録。キー値は出力しない）。
  3. 「お辞儀して」等の1指示から、確定済みschema準拠の計画JSONが得られ、
     ローカルvalidatorで合格するか。

このスクリプトはまだ ROS 2 パッケージではない（Task 1 のゲート専用）。
合格後、Task 2 で client / validator のロジックを ROS 2 パッケージへ移植する。
ROS 2 へのJointTrajectory送信はこのスクリプトでは一切行わない（繋がるか確認するだけ）。

前提:
  - GEMINI_API_KEY が環境変数に設定済み（Mac側 .secrets/gemini.env を docker cp で
    コンテナの ~/gemini.env へ置き、source する。docs/gemini-api-key-setup.md 参照）。
  - 依存: pip install google-genai pydantic （Task 1 でユーザー承認後に導入）。

実行例:
  set -a; source ~/gemini.env; set +a
  python3 gemini_connection_check.py
"""

from __future__ import annotations

import os
import sys
import time
from enum import Enum
from typing import Literal

try:
    from pydantic import BaseModel, Field, ValidationError, conint, conlist
except ImportError:
    print("pydantic が未導入です。`pip install pydantic` が必要です。", file=sys.stderr)
    raise

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("google-genai が未導入です。`pip install google-genai` が必要です。", file=sys.stderr)
    raise


# --- 確定済みスキーマ（docs/preset-and-schema-design.md 3節に一致させる） -----------
# 上限値: actions配列長<=5 / repetitions<=3 / preset列挙は3種 / direction列挙は2種。

MAX_ACTIONS = 5
MAX_REPETITIONS = 3


class Preset(str, Enum):
    bow = "bow"
    rotate_base = "rotate_base"
    wave = "wave"


class Direction(str, Enum):
    left = "left"
    right = "right"


# 受信検証用モデル（厳格）。LLM出力は信頼せず、未知フィールドを拒否する。
# 注意: Geminiの response_schema は additionalProperties を受け付けないため、
#       extra:forbid はここ（受信検証）だけに付け、送信用スキーマ(下記)には付けない。
class Parameters(BaseModel):
    """プリセット別の許可パラメータ。未知フィールドは拒否する（受信検証）。"""

    model_config = {"extra": "forbid"}  # additionalProperties: false 相当

    # bow / wave 用（整数 1..MAX_REPETITIONS）。rotate_base では使わない。
    repetitions: conint(ge=1, le=MAX_REPETITIONS) | None = None
    # rotate_base 用（left/right）。bow / wave では使わない。
    direction: Direction | None = None


class Action(BaseModel):
    model_config = {"extra": "forbid"}

    preset: Preset
    parameters: Parameters = Field(default_factory=Parameters)


class Plan(BaseModel):
    """LLMが返す動作計画（受信検証）。version + 順序付きactions配列。"""

    model_config = {"extra": "forbid"}

    version: Literal["1.0"]
    actions: conlist(Action, min_length=1, max_length=MAX_ACTIONS)


# 送信用スキーマ（Gemini response_schema 用）。extra:forbid を付けない。
# 出力の型を縛るのが役割で、未知フィールド拒否は受信側の Plan が担う（二重防御）。
class ParametersOut(BaseModel):
    repetitions: conint(ge=1, le=MAX_REPETITIONS) | None = None
    direction: Direction | None = None


class ActionOut(BaseModel):
    preset: Preset
    parameters: ParametersOut = Field(default_factory=ParametersOut)


class PlanOut(BaseModel):
    version: Literal["1.0"]
    actions: conlist(ActionOut, min_length=1, max_length=MAX_ACTIONS)


# --- プリセット別パラメータの整合チェック（スキーマだけでは縛れない部分） ----------

def validate_plan_semantics(plan: Plan) -> list[str]:
    """各プリセットが許可パラメータだけを持つか検査する。問題点のリストを返す。"""
    errors: list[str] = []
    for i, action in enumerate(plan.actions):
        p = action.parameters
        if action.preset in (Preset.bow, Preset.wave):
            if p.direction is not None:
                errors.append(f"actions[{i}] {action.preset.value}: direction は許可されない")
            # repetitions は任意（未指定なら1回扱い）
        elif action.preset == Preset.rotate_base:
            if p.direction is None:
                errors.append(f"actions[{i}] rotate_base: direction が必須")
            if p.repetitions is not None:
                errors.append(f"actions[{i}] rotate_base: repetitions は許可されない")
    return errors


# --- Gemini 呼び出し ---------------------------------------------------------------

SYSTEM_PROMPT = (
    "あなたはロボットアームの動作計画器です。ユーザーの日本語指示を、"
    "許可された3つのプリセット(bow, rotate_base, wave)の選択・順序・パラメータだけから成る"
    "JSON計画に変換します。生の関節角・速度・トピック名・説明文は一切出力しないでください。"
    "rotate_base には direction(left/right) を、bow と wave には必要なら repetitions(1..3) を付けます。"
    "対応できない指示や危険な指示は、空のactionsではなく、変換せずエラーとして扱われます。"
)


def main() -> int:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("GEMINI_API_KEY が未設定です。docs/gemini-api-key-setup.md を参照。", file=sys.stderr)
        return 2

    # モデルIDは実行時に最新の無料対象を確認して差し替える（Task 1）。
    model_id = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
    instruction = sys.argv[1] if len(sys.argv) > 1 else "お辞儀して"

    client = genai.Client(api_key=api_key)

    t0 = time.monotonic()
    try:
        response = client.models.generate_content(
            model=model_id,
            contents=instruction,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=PlanOut,
                temperature=0.0,  # 再現性のため固定
            ),
        )
    except Exception as exc:  # 接続/認証/timeout 等
        dt = time.monotonic() - t0
        # 例外メッセージにキーが含まれないよう型と概要だけ出す
        print(f"[NG] 推論失敗 ({dt:.2f}s): {type(exc).__name__}", file=sys.stderr)
        return 1
    dt = time.monotonic() - t0

    raw = (response.text or "").strip()
    print(f"[OK] 接続・推論成功 ({dt:.2f}s)")
    print("--- raw応答 ---")
    print(raw)

    # ローカルvalidatorで合格するか（LLM出力は信頼しない）
    try:
        plan = Plan.model_validate_json(raw)
    except ValidationError as exc:
        print("[NG] スキーマ検証に失敗（ロボットへは送らない）", file=sys.stderr)
        print(exc, file=sys.stderr)
        return 1

    sem_errors = validate_plan_semantics(plan)
    if sem_errors:
        print("[NG] パラメータ整合に失敗（ロボットへは送らない）", file=sys.stderr)
        for e in sem_errors:
            print("  - " + e, file=sys.stderr)
        return 1

    print("--- canonical plan（検証合格） ---")
    print(plan.model_dump_json(indent=2, exclude_none=True))
    print("[GATE] 3点(接続・推論・妥当JSON)クリア。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
