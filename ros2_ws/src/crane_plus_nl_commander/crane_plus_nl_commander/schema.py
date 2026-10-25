"""動作計画(JSON)のスキーマ・意味検証・正規化。

design.md 3.4（検証順序）と docs/preset-and-schema-design.md 3節（スキーマ上限）に対応する。
LLM出力は信頼しない外部入力として扱い、二重防御する:
  - 送信用スキーマ(PlanOut): Geminiの response_schema 用。additionalProperties を出さない
    （Geminiが additionalProperties を含むスキーマに 400 INVALID_ARGUMENT を返すため）。
  - 受信検証(Plan): extra="forbid" で未知フィールドを拒否し、型・列挙・上限を厳格に検査する。

このモジュールは ROS 2 にも Gemini SDK にも依存しない（単体テスト可能）。
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, conint, conlist

# --- 上限値（docs/preset-and-schema-design.md 3.2 に一致させる） --------------------
MAX_ACTIONS = 5
MAX_REPETITIONS = 5
MAX_RESPONSE_BYTES = 2048  # 応答サイズ上限（design 3.4 手順1）
MAX_TOTAL_PLAN_SEC = 45.0  # 計画全体の見積総時間上限（3.2）


class Preset(str, Enum):
    bow = "bow"
    nod = "nod"
    cheer = "cheer"
    wave = "wave"
    rotate_base = "rotate_base"
    grip = "grip"


class Direction(str, Enum):
    left = "left"
    right = "right"


# --- 受信検証用モデル（厳格・未知フィールド拒否） -----------------------------------
class Parameters(BaseModel):
    """プリセット別の許可パラメータ。未知フィールドは拒否する。"""

    model_config = {"extra": "forbid"}  # additionalProperties: false 相当

    repetitions: conint(ge=1, le=MAX_REPETITIONS) | None = None  # bow / wave 用
    direction: Direction | None = None  # rotate_base 用


class Action(BaseModel):
    model_config = {"extra": "forbid"}

    preset: Preset
    parameters: Parameters = Field(default_factory=Parameters)


class Plan(BaseModel):
    """LLMが返す動作計画（受信検証）。version + 順序付きactions配列。"""

    model_config = {"extra": "forbid"}

    version: Literal["1.0"]
    actions: conlist(Action, min_length=1, max_length=MAX_ACTIONS)


# --- 送信用スキーマ（Gemini response_schema 用。extra:forbid を付けない） -----------
class ParametersOut(BaseModel):
    repetitions: conint(ge=1, le=MAX_REPETITIONS) | None = None
    direction: Direction | None = None


class ActionOut(BaseModel):
    preset: Preset
    parameters: ParametersOut = Field(default_factory=ParametersOut)


class PlanOut(BaseModel):
    version: Literal["1.0"]
    actions: conlist(ActionOut, min_length=1, max_length=MAX_ACTIONS)


class ValidationFailure(Exception):
    """検証失敗。理由（秘密を含まない）を保持する。実行器は呼ばれない。"""

    def __init__(self, reasons: list[str]) -> None:
        self.reasons = reasons
        super().__init__("; ".join(reasons))


# repetitions を許可するプリセット（direction は不可）。rotate_base のみ direction。
REPS_PRESETS = (Preset.bow, Preset.nod, Preset.cheer, Preset.wave, Preset.grip)


def validate_plan_semantics(plan: Plan) -> list[str]:
    """各プリセットが許可パラメータだけを持つか検査する。問題点のリストを返す。"""
    errors: list[str] = []
    for i, action in enumerate(plan.actions):
        p = action.parameters
        if action.preset in REPS_PRESETS:
            if p.direction is not None:
                errors.append(f"actions[{i}] {action.preset.value}: direction は許可されない")
            # repetitions は任意（未指定なら1回扱い）
        elif action.preset == Preset.rotate_base:
            if p.direction is None:
                errors.append(f"actions[{i}] rotate_base: direction が必須")
            if p.repetitions is not None:
                errors.append(f"actions[{i}] rotate_base: repetitions は許可されない")
    return errors


def validate_response(raw: str, estimate_seconds=None) -> Plan:
    """LLMのraw応答文字列を検証し、合格した Plan を返す。

    design.md 3.4 の順序: 応答サイズ → parse/schema → 意味検証 → 計画全体の見積時間。
    どこか1段でも失敗したら ValidationFailure を送出する（実行器は呼ばない）。

    estimate_seconds: Plan を受け取り見積総時間(秒)を返す関数（任意）。
      presetの軌道定義に依存するため、呼び出し側（ノード）から注入する。
      None のときは見積時間検査をスキップする（純粋なschema検証のみ）。
    """
    if len(raw.encode("utf-8")) > MAX_RESPONSE_BYTES:
        raise ValidationFailure([f"応答サイズが上限({MAX_RESPONSE_BYTES}B)を超過"])

    try:
        plan = Plan.model_validate_json(raw)
    except Exception as exc:  # pydantic ValidationError / JSON decode error
        raise ValidationFailure([f"スキーマ検証に失敗: {type(exc).__name__}"]) from exc

    sem_errors = validate_plan_semantics(plan)
    if sem_errors:
        raise ValidationFailure(sem_errors)

    if estimate_seconds is not None:
        total = estimate_seconds(plan)
        if total > MAX_TOTAL_PLAN_SEC:
            raise ValidationFailure(
                [f"計画全体の見積時間 {total:.1f}s が上限({MAX_TOTAL_PLAN_SEC}s)を超過"]
            )

    return plan


def to_canonical_json(plan: Plan) -> str:
    """検証済み計画を正規化した canonical JSON 文字列にする（表示・再現性用）。

    exclude_none で未指定パラメータを落とし、キー順を安定させる。
    """
    return plan.model_dump_json(indent=2, exclude_none=True)
