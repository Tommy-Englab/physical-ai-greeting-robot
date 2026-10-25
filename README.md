# Physical AI 応用1 最終課題 — あいさつコミュニケーションロボット

自然言語の指示をLLMが安全な動作計画（JSON）へ変換し、検証を通ったものだけをGazebo上のロボットアーム CRANE+ V2 が実行する作品です。

テーマは「**あいさつコミュニケーションロボット**」。少数の安全な動作しか持たないロボットアームでも、AIが人の言葉（あいさつ・感情）の意図を汲んで動作を組み合わせれば、意思疎通や好感を感じさせる振る舞いになるか、を試みます。

- 例（動作名の直接指定）: 「右を向いてからお辞儀して」→ LLMが許可済みプリセットの選択・順序・回数をJSONで出力 → validatorが検証 → ROS 2 `JointTrajectory` へ変換 → Gazebo上のCRANE+ V2が実行
- 例（あいさつ・感情の解釈）: 「こんにちは」→ 会釈、「うれしい！」→ 喜び＋手を振る、「ありがとう」→ 丁寧なお辞儀

LLMには生の関節角や制御コマンドを生成させません。安全確認済みのプリセット動作の**選択・順序・制限付きパラメータだけ**をJSONで返させ、検証に合格した計画のみをロボットへ送ります。この安全境界と、プリセットの組み合わせ・系列による感情表現が本作品の工夫点です。

## プリセット動作（6種）

各動作は CRANE+ V2 の異なる関節を主役にして、見分けられるように設計しています。

| プリセット | 主役の関節 | 動き | おおまかな意味 |
|---|---|---|---|
| `bow` | 肩 (joint2) 前傾 | お辞儀 | 挨拶・感謝 |
| `nod` | 肩 (joint2) 浅く速く | うなずき | 同意・肯定 |
| `cheer` | 肘 (joint3) 跳ね上げ | 腕を上げて喜ぶ | 喜び・歓喜 |
| `wave` | 手首 (joint4) 左右 | 手を振る | 挨拶・別れ |
| `rotate_base` | 基部 (joint1) 旋回 | 左右を向く | 注目・振り向く |
| `grip` | グリッパ (joint_hand) 開閉 | 指を開閉 | 受け取る・呼応 |

`bow` / `nod` / `cheer` / `wave` / `grip` は回数 `repetitions`（1〜5）、`rotate_base` は方向 `direction`（left / right）をパラメータに取ります。AIは「感情が強いほど回数を増やす」といった形で、動作の組み合わせ・回数により感情の強さを表現します。

## 課題要件との対応

- AIの利用（推論のみで可）: 自然言語 → 動作計画JSON への変換にLLM（Google Gemini）推論を使用
- タスク: 自然言語指示に従った複数動作の実行（あいさつ・感情への応答、およびその組み合わせ）
- 提出物: 実行動画（MP4, 1〜3分）、コード一式（GitHub public）、レポート（PDF）

課題条件の全文は [`docs/spec/course-requirements.md`](docs/spec/course-requirements.md) を参照。要件・設計・タスクは [`docs/spec/`](docs/spec/) にまとめている。

## システム構成

```text
[自然言語の指示（あいさつ・感情を含む）]
      ↓
[LLM推論 (Gemini)]  許可済み6プリセットの選択・順序・回数・方向のみをJSON出力
      ↓
[Validator]         スキーマ・意味・上限・可動範囲・計画時間を多段検証（不合格なら停止）
      ↓
[プリセット実行器]   検証済み計画を順に実行（各動作の完了を待って次へ）
      ↓
[ROS 2変換]         trajectory_msgs/JointTrajectory へ変換
      ↓
[Gazebo上のCRANE+ V2]  armは arm_controller、gripはgripper_controllerへ送信
```

ROSパッケージ `crane_plus_nl_commander`（本リポジトリ `ros2_ws/src/`。コンテナ内では `/workspace/ros2_ws/src/` に配置して使う）の主なモジュール:

- `schema.py` — 送信/受信の二重防御スキーマ、意味検証、canonical化
- `llm_client.py` — Gemini client（timeout・再試行、差し替え可能）
- `presets.py` — 6プリセットの軌道定義と可動範囲検査
- `trajectory_builder.py` — プリセット → `JointTrajectory` 変換
- `nl_commander.py` — ノード本体（live / saved モード）

## 開発環境

講座公式のDocker環境を利用します。

- イメージ: `airobotbook/ros2-desktop-ai-robot-book-humble:latest`
- ROS 2 Humble / Gazebo Sim 6 / CRANE+ V2
- 操作はブラウザ `http://localhost:6080/` のデスクトップ（noVNC）経由
- LLM: Google Gemini（Developer API 無料枠、SDK `google-genai`）

環境の立ち上げ・再開・停止・トラブル対処の手順は [`docs/docker-guide.md`](docs/docker-guide.md) にまとめています。

## 実行方法

### 1. 依存の導入（コンテナ内、初回のみ）

```bash
pip3 install google-genai pydantic
```

### 2. APIキーの設定（値はコミットしない）

Google AI Studio で発行したキーを環境変数 `GEMINI_API_KEY` に設定します。キーは `.secrets/gemini.env`（`.gitignore` 済み）などに置き、実行シェルで読み込みます。取得・設定の手順は [`docs/gemini-api-key-setup.md`](docs/gemini-api-key-setup.md) を参照。

```bash
set -a; source ~/gemini.env; set +a   # GEMINI_API_KEY を読み込む
```

### 3. ビルドと起動

```bash
# ROS 2 環境の読み込み（新しいシェルごとに毎回）
source /opt/ros/humble/setup.bash
source ~/airobot_ws/install/setup.bash

# Gazebo + CRANE+ V2 を起動（ブラウザGUIのターミナルから）
ros2 launch crane_plus_gazebo crane_plus_with_table.launch.py
```

別のシェルでコマンダを実行します。

```bash
source /opt/ros/humble/setup.bash
source ~/airobot_ws/install/setup.bash
source /workspace/ros2_ws/install/setup.bash
set -a; source ~/gemini.env; set +a

# live モード（Geminiに推論させる）
ros2 run crane_plus_nl_commander nl_commander "こんにちは"

# 検証済み計画を保存して後で再生（API障害時の保険）
ros2 run crane_plus_nl_commander nl_commander "うれしい！" --save /workspace/plans/happy.json
ros2 run crane_plus_nl_commander nl_commander --saved /workspace/plans/happy.json
```

実行すると、検証に合格した計画が canonical JSON としてログに表示され、その順序・方向・回数どおりにGazeboのCRANE+ V2が動作します。未対応・危険・不正な指示は検証で停止し、ロボットへは一切送られません。

### テスト

```bash
cd /workspace/ros2_ws
colcon build --packages-select crane_plus_nl_commander
python3 -m pytest src/crane_plus_nl_commander/test/
```

## 安全設計

- LLMには関節角・速度・トピック名などの生の制御値を生成させず、プリセットの選択・順序・回数・方向だけを出させます。
- LLMの出力は信頼しない外部入力として扱い、応答サイズ → JSONパース → スキーマ（型・列挙・配列長・回数・未知フィールド）→ 意味（プリセット別の許可パラメータ）→ プリセットの可動範囲 → 計画全体の見積時間、の順に多段検証します。
- どの段で失敗しても `JointTrajectory` は送信されません（安全停止）。
- 再現性のため `temperature=0` と構造化出力（JSONスキーマ）を用い、検証後の計画をcanonical JSONへ正規化します。

## ライセンス / 注意

- APIキー等の秘密情報はコミットしない（`.secrets/` に置き `.gitignore` で除外）。
- 公開できないデータや再配布権のない講座・コンペ由来資産は含めない（提出物は受講者へ公開される可能性があるため）。
- 氏名・所属・メール等の個人情報を成果物に含めない。
