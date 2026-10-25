"""LLM client（Gemini）。自然言語 → raw JSON文字列（untrusted）。

design.md 3.2 / 3.5 / 3.6 に対応。
- 構造化出力に送信用スキーマ PlanOut を使う（schema.py）。
- 計画生成中のみ最大2回まで再試行（503 等の一時障害向け）。ロボット実行中は呼ばない。
- API応答timeout（既定15s）を超えたら例外。キー値・認証オブジェクトは出力しない。

テスト容易性のため PlanGenerator プロトコルで抽象化し、
コンポーネントテストでは Gemini を使わないフェイクを注入できる。
"""

from __future__ import annotations

import os
import time
from typing import Protocol

from .schema import PlanOut

# 既定値（docs/preset-and-schema-design.md 4節）
DEFAULT_MODEL = "gemini-flash-latest"
API_TIMEOUT_SEC = 15.0
MAX_RETRIES = 2  # 計画生成中のみ

SYSTEM_PROMPT = (
    "あなたは『あいさつコミュニケーションロボット』の動作計画器です。"
    "ユーザーの日本語（あいさつ・感情表現を含む）を、許可された5つのプリセットの"
    "選択・順序・パラメータだけから成るJSON計画に変換します。"
    "生の関節角・速度・トピック名・説明文は一切出力しないでください。\n"
    "プリセット: bow(お辞儀/会釈/感謝), nod(うなずく/同意/はい), cheer(喜ぶ/腕を上げる/万歳), "
    "wave(手を振る/挨拶/別れ), rotate_base(左右を向く), grip(グリッパ開閉/受け取る/呼応)。\n"
    "パラメータ: rotate_base には direction(left/right) を付けます。"
    "bow/nod/cheer/wave/grip には必要なら repetitions(1..5) を付けます（感情が強いほど多めに）。\n"
    "動作名が直接書かれていればそのプリセットを選びます。"
    "あいさつ語・感情のときは好感度の高い動作列へ翻訳します。例:\n"
    "  「こんにちは」→ bow を1回\n"
    "  「ありがとう」→ bow を2回（丁寧に）\n"
    "  「うれしい！」→ cheer を2回、続けて wave を2回\n"
    "  「はい」「そうだね」→ nod を2回\n"
    "  「やったー」→ cheer を3回\n"
    "  「またね」「バイバイ」→ wave を2回\n"
    # --- 境界ポリシー（docs/preset-and-schema-design.md 5.4。A採用。B へは下行を差し替え） ---
    # A（創造許容・採用）:
    "6プリセットの組み合わせで安全に表現できる指示は、たとえ動作名が直接書かれていなくても"
    "創造的に翻訳してよい（例「踊って」→左右を向く・手を振る・うなずくの組み合わせ）。"
    "ただし6プリセットでは物理的に表現できない動作（物を掴んで運ぶ・歩く・移動する等）や、"
    "生の制御値（関節角・速度・トピック名）の指定は、空のactionsではなく変換せずエラーとして扱われます。"
    # B（厳密停止・不採用）に切り替える場合は上の2文を次の1文に置換:
    # "明示的に対応づけた動作名・あいさつ語・感情表現に該当しない指示は、変換せずエラーとして扱われます。"
)


class PlanGenerator(Protocol):
    """自然言語指示 → raw JSON文字列 を返す抽象。"""

    def generate(self, instruction: str) -> str:
        ...


class LLMError(Exception):
    """API接続・認証・timeout 等の失敗。秘密を含まないメッセージだけ持つ。"""


class GeminiPlanGenerator:
    """google-genai を使う本番実装。"""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout_sec: float = API_TIMEOUT_SEC,
        max_retries: int = MAX_RETRIES,
    ) -> None:
        key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not key:
            raise LLMError("GEMINI_API_KEY が未設定です")
        # 遅延importでROS側の起動を軽くする
        from google import genai

        self._genai = genai
        self._client = genai.Client(api_key=key)
        self._model = model or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
        self._timeout_ms = int(timeout_sec * 1000)
        self._max_retries = max_retries

    def generate(self, instruction: str) -> str:
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=PlanOut,
            temperature=0.0,  # 再現性のため固定（design 2.4）
            http_options=types.HttpOptions(timeout=self._timeout_ms),
        )

        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.models.generate_content(
                    model=self._model,
                    contents=instruction,
                    config=config,
                )
                return (response.text or "").strip()
            except Exception as exc:  # 接続/認証/timeout/一時障害
                last_exc = exc
                if attempt < self._max_retries:
                    time.sleep(1.0 * (attempt + 1))  # 単純バックオフ
                    continue
        # 再試行しても失敗。型名だけ出す（キーを漏らさない）
        raise LLMError(
            f"推論失敗（{self._max_retries + 1}回試行）: "
            f"{type(last_exc).__name__ if last_exc else 'unknown'}"
        )
