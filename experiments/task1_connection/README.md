# Task 1 接続ゲート用の実験スクリプト

tasks.md の **Task 1（接続・最小推論ゲート）** 専用。コンテナ `pai_ros2` から Gemini へ
繋がるか、最小推論が通るか、確定済みschema準拠の計画JSONが得られるかを最短で確かめる。

- これは ROS 2 パッケージではない。合格後、Task 2 で client / validator のロジックを
  公式scaffoldで作る ROS 2 パッケージへ移植する。
- このスクリプトは **ROS 2 への JointTrajectory 送信を一切行わない**（繋がるか確認するだけ）。

## 前提

1. ユーザーが Gemini APIキーを発行し環境変数に設定済み（`docs/gemini-api-key-setup.md`）。
2. 依存を導入済み（Task 1 でユーザー承認後）:
   ```bash
   pip install google-genai pydantic
   ```

## 実行

```bash
set -a; source ~/gemini.env; set +a
python3 gemini_connection_check.py            # 既定の指示「お辞儀して」
python3 gemini_connection_check.py "右を向いてからお辞儀して"
```

- モデルIDは `GEMINI_MODEL` 環境変数で差し替え可（既定 `gemini-flash-latest`）。
  実行時に最新の無料対象モデルを公式で確認して指定する。

## 合格判定（撤退ゲート）

着手から1〜2時間以内に次の3点が通れば合格、Task 2 へ進む。通らなければ原因と試した
公式手順を記録し、ユーザーとB案継続・別モデル・ACT系復帰を再判断する（勝手に方針変更しない）。

1. `[OK] 接続・推論成功` が出る（HTTPS接続＋最小推論）。
2. raw応答が得られる。
3. `[GATE] 3点...クリア` が出る（schema検証＋パラメータ整合に合格）。

異常系（キー未設定・接続失敗・不正JSON）では、いずれも検証前後で停止し、ロボットへは何も送らない。

## 確定済みスキーマ

スクリプト内の Pydantic モデルは `docs/preset-and-schema-design.md` 3節の確定値に一致させている
（preset 3種・direction 2種・repetitions 1..3・actions 1..5・未知フィールド拒否）。
設計値を変える場合は両方を同時に直す。
