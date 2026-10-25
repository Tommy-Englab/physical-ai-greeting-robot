# E2Eデモ・録画手順書（Task 3/6 のGazebo目視と動画撮影用）

> RPD回復日（無料枠 RPD=20 がフル使える日）に、最短・最小回数でGazebo目視と録画を終えるための手順。
> 投げる指示を事前確定し、live推論の回数を節約する。正本の設計は requirements 1.1 / preset-and-schema-design.md / tasks.md。

## 0. 重要な制約（必ず意識する）

- 無料枠 **RPD=20（1日20リクエスト）/ RPM=5（1分5回）**。live実行はこの範囲。やり直しを見込み、1日で使い切らない計画にする。
- 503（Google側高負荷）が出たら時間を置くか `export GEMINI_MODEL=gemini-3.8-flash` でモデル変更。
- 429（枠超過）が出たら RPM=1分 / RPD=翌日（UTC-8リセット）まで待つ。
- **保険**: live が叩けない日は `--saved` で検証済み計画を再生できる（動画には `saved` と明記）。

## 1. 事前準備（コンテナ・キー）

ホスト側（Mac）でコンテナ起動とキー配置（Kiroが実施可）:

```bash
docker start pai_ros2
docker cp .secrets/gemini.env pai_ros2:/home/ubuntu/gemini.env   # 既に配置済みなら不要
docker exec -u root pai_ros2 bash -lc 'chown ubuntu:ubuntu /home/ubuntu/gemini.env; chmod 600 /home/ubuntu/gemini.env'
```

## 2. Gazebo起動（ブラウザGUIのTerminator、シェル1）

> docker exec の背景起動はSIGKILLで落ちるため、必ずブラウザGUI（http://localhost:6080/）から手動起動する。

```bash
source /opt/ros/humble/setup.bash
source ~/airobot_ws/install/setup.bash
ros2 launch crane_plus_gazebo crane_plus_with_table.launch.py
```

CRANE+ V2 が表示され、controller が spawn されるまで待つ（ログが落ち着くまで）。

## 3. コマンダ実行（シェル2）

```bash
source /opt/ros/humble/setup.bash
source ~/airobot_ws/install/setup.bash
source /workspace/ros2_ws/install/setup.bash
set -a; source ~/gemini.env; set +a
```

### 3.1 録画で見せる指示リスト（確定・この順で実行）

テーマ「あいさつコミュニケーションロボット」。動作名直指定→感情解釈→安全停止の順で、AIの判断の幅を見せる。
各 live 実行は1リクエスト消費。`--save` で後日saved再生用に保存しておくと保険になる。

| # | コマンド | 見せたいこと | 消費 |
|---|---|---|---|
| 1 | `ros2 run crane_plus_nl_commander nl_commander "お辞儀して" --save /workspace/plans/01_bow.json` | 直指定・単発（bow） | 1 |
| 2 | `ros2 run crane_plus_nl_commander nl_commander "右を向いてからお辞儀して" --save /workspace/plans/02_turn_bow.json` | 直指定・順序分解（rotate_base→bow） | 1 |
| 3 | `ros2 run crane_plus_nl_commander nl_commander "左を向いて2回手を振って" --save /workspace/plans/03_turn_wave.json` | 方向＋回数（rotate_base(left)→wave×2） | 1 |
| 4 | `ros2 run crane_plus_nl_commander nl_commander "こんにちは" --save /workspace/plans/04_hello.json` | 感情解釈（あいさつ→bow 会釈） | 1 |
| 5 | `ros2 run crane_plus_nl_commander nl_commander "うれしい！" --save /workspace/plans/05_happy.json` | 感情解釈（喜び→cheer×2→wave×2）主役シーン | 1 |
| 6 | `ros2 run crane_plus_nl_commander nl_commander "ありがとう" --save /workspace/plans/06_thanks.json` | 感情解釈（感謝→深めのbow×2） | 1 |
| 7 | `ros2 run crane_plus_nl_commander nl_commander "そうだね" --save /workspace/plans/07_nod.json` | 感情解釈（同意→nod）※bowと深さ・速さの違いを見せる | 1 |
| 8 | `ros2 run crane_plus_nl_commander nl_commander "物を掴んで"` | 安全停止（primitiveに落とせない→Reject・無動作） | 1 |

- `grip`（グリッパ開閉）は単独では地味なので、録画では上記の感情解釈の中でAIが選べば映す程度でよい。明示的に見せたいなら「受け取って」等を1リクエスト足す（任意）。
- 合計8リクエスト（RPD=20内。やり直し余地あり）。RPM=5なので**1分に5回まで**。6回目以降は1分空けるか、数十秒間隔で。
- 各コマンド実行後、Gazeboで動作を目視。ログの「検証合格。canonical plan」のJSONも画面に映す（AI出力の可視化）。
- #8「物を掴んで」は動かないのが正解（ログに `[停止]`）。「AIが安全境界で止まる」ことの実演。

### 3.2 saved再生（live温存 or 本番保険。消費ゼロ）

一度 `--save` した計画は、live を使わず再生できる:

```bash
ros2 run crane_plus_nl_commander nl_commander --saved /workspace/plans/05_happy.json
```

ログに `[MODE: saved]` が出る。動画で saved を使う場合は必ずその旨を明記（live成功として扱わない）。

## 4. 録画（Gazebo Video Recorder）

- Gazeboウィンドウを前面にし、3D sceneウィンドウを広げる（解像度はウィンドウ依存）。
- 右下 Video recorder もしくは右上3点メニュー → Video Recorder → MP4録画開始。
- 保存先に `/workspace` を指定（ホスト `workspace/` に反映）。
- 全画面の ffmpeg x11grab は使わない（RViz/terminal/taskbarが映る）。
- 動画は1〜3分・2倍速まで。倍速時は動画内または概要欄に明記。

## 5. 目視チェックリスト（Task 3 完了条件）

- [ ] 各指示でcanonical JSONの順序・方向・回数どおりに動く
- [ ] 6プリセットが互いに見分けられる（bow=前傾/nod=浅く速い/cheer=跳ね上げ/wave=手首左右/rotate_base=向き変え/grip=開閉）
- [ ] 各動作が開始ニュートラルから動き、終了時にニュートラルへ戻る
- [ ] 感情解釈（こんにちは/うれしい/ありがとう/そうだね）が好感度高く見える
- [ ] #8「物を掴んで」で無動作（安全停止）
- [ ] 動きが安全（急な動き・机への突っ込みがない）

> カメラアングル: 俯瞰（斜め上からテーブル天板を見下ろす）だとアーム全体が見える。横からだとテーブル脚とアームが重なって見分けにくい。録画前に3Dビューを俯瞰に調整する（GUIでドラッグ、または `/gui/move_to/pose` サービス）。

## 6. トラブル対処

- `Too many open files` / Gazebo や RViz が exit -6 → `docker restart pai_ros2`（コンテナ内成果物は保持）。
- `ros2: command not found` → source 3点（opt/ros, airobot_ws, pai_ws または ros2_ws）を忘れている。
- 503 → 時間を置く / `export GEMINI_MODEL=gemini-3.8-flash`。
- 429 → RPM(1分) か RPD(翌日) まで待つ。saved再生で代替。
- 動きが意図と違う（姿勢） → `presets.py` の該当 build_* の rad 値を目視で調整し `colcon build`。
