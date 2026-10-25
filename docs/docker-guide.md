# Docker操作手順書（講座演習環境）

> 講座公式Dockerコンテナ `pai_ros2` の立ち上げ・運用手順。次セッションでもこれだけ見れば環境を再現・操作できる。
> 2026-10-11時点の実コンテナ設定に基づく。

## 0. 前提

- ホスト: Mac（Apple Silicon / arm64）、Docker Desktop。
- イメージ: `airobotbook/ros2-desktop-ai-robot-book-humble:latest`（約25GB、取得済み）。linux/amd64をRosetta経由で実行。
- コンテナ名: `pai_ros2`。
- 操作はブラウザ `http://localhost:6080/` でコンテナ内Linuxデスクトップ（noVNC）を使う。

## 1. まず状態を確認する

```bash
# Docker Desktopが起動しているか
docker info >/dev/null 2>&1 && echo "docker OK" || open -a Docker

# コンテナの有無と状態
docker ps -a --format '{{.Names}} | {{.Status}}' | grep pai_ros2 || echo "pai_ros2 なし(初回run必要)"
```

- `Up ...` → 稼働中。そのままブラウザ `http://localhost:6080/` へ。
- `Exited ...` → 停止中。「3. 再開」へ。
- 表示されない → 未作成。「2. 初回作成」へ。

## 2. 初回作成（コンテナが無いとき）

ワークスペース直下で実行する。`workspace/` をコンテナの `/workspace` にマウントする（成果物をMac側に残すため）。

```bash
cd <このリポジトリをcloneしたディレクトリ>
mkdir -p workspace
docker run -d --name pai_ros2 \
  --platform linux/amd64 \
  -p 6080:80 \
  -p 9090:9090 -p 9876:9876 \
  --shm-size=512m \
  -v "$(pwd)/workspace":/workspace \
  airobotbook/ros2-desktop-ai-robot-book-humble:latest
```

- `-p 6080:80`: ブラウザデスクトップ。
- `-p 9090:9090 -p 9876:9876`: 可視化ツール rerun 用。
- `--shm-size=512m`: Gazebo向け共有メモリ。
- `-v .../workspace:/workspace`: Mac↔コンテナ共有フォルダ。

起動後、ブラウザで `http://localhost:6080/` を開き「接続」。Mozc変換エンジンエラーが出たら閉じてよい（既知の警告）。

## 3. 再開（停止中のコンテナを使う）

```bash
docker start pai_ros2
# 数秒待ってブラウザ http://localhost:6080/ を開く
```

初回の `docker run` は一度だけ。2回目以降は必ず `docker start`（`run` を再実行すると名前重複エラー）。

## 4. 停止（リソース解放）

```bash
docker stop pai_ros2
```

- 作業内容（`~/pai_ws`, `~/airobot_ws`, `~/pai_training`, `~/dataset`, `~/checkpoints` 等）は保持される。
- Exit 137 は `docker stop` による正常終了。異常ではない。

## 5. トラブル対処

### Gazebo/RVizが "Too many open files" や exit -6 で落ちる
起動/停止を繰り返すとファイルハンドルが枯渇する。モデルや起動コマンドを推測で変えず、コンテナを再起動する。

```bash
docker restart pai_ros2
```

作業内容は再起動で保持される。

### Gazeboの起動方法
Gazeboはブラウザ内のTerminatorから手動で起動する（例: `ros2 launch ...`）。エージェントが `docker exec` でバックグラウンド起動すると、controller起動直後にGazebo serverがSIGKILLで落ちる実績があるため使わない。

### コンテナが応答しない/壊れたとき
最終手段としてコンテナを作り直す。ただし `docker rm` するとコンテナ内の変更は全て消える（`/workspace` のMac側だけ残る）。安易に実行しない。

```bash
docker rm -f pai_ros2   # 破壊的。中身が消える。本当に作り直すときだけ
# その後「2. 初回作成」からやり直す
```

## 6. ファイルの受け渡し

- Mac → コンテナ / コンテナ → Mac は `/workspace`（Mac側 `workspace/`）経由が最も簡単。残したい成果物はここに置く。
- コンテナ内の任意パスから取り出す場合: `docker cp pai_ros2:/home/ubuntu/xxx ./`

## 7. コンテナ内のよく使う定型

```bash
# ROS 2 を使う前（ターミナルごとに必要）
source /opt/ros/humble/setup.bash
source ~/airobot_ws/install/setup.bash
source ~/pai_ws/install/setup.bash

# 録画: Gazebo標準のVideo Recorder（右下パネル/3点メニュー）。保存先は /workspace を指定。
```

## 8. 実コンテナ設定（2026-10-11確認、参考値）

- image: `airobotbook/ros2-desktop-ai-robot-book-humble:latest`
- ports: `6080->80`, `9090->9090`, `9876->9876`
- mount: `.../physical-ai-final-project/workspace` → `/workspace`（RW）
- shm-size: 512MB

## 9. コンテナ内にのみ存在する成果物（消滅リスクあり）

次の成果物はコンテナ `pai_ros2` 内にのみ存在し、git にも Mac 側の `workspace/` にも無い。`docker rm` すると消える（`docker stop` / `start` では保持される）。現行B案（LLM→プリセット）では基本的に使わないが、旧ACT実証の事実はレポートの「試行錯誤・考察」の材料になり、B案が頓挫した場合のACT系への復帰にも使うため、不用意に削除しない。

| パス（コンテナ内） | 内容 | B案での用途 |
|---|---|---|
| `~/pai_ws/src/physicalai_teleop` | テレオペpkg（クローン・ビルド済み） | 使わない |
| `~/pai_training` | pixi環境（約8GB）＋ACT学習コード一式 | 使わない |
| `~/dataset/rosbags/` | お辞儀デモ（ep0）の収集済みrosbag | 使わない（レポート材料） |
| `~/dataset/lerobot_dataset/crane_plus_pekori/` | 変換済みLeRobotデータセット | 使わない（レポート材料） |
| `~/checkpoints/train/crane_plus_pekori_act/` | 学習済みACTモデル（model.safetensors + config） | 使わない（レポート材料） |
| `~/airobot_ws/.../worlds/table_peg.sdf`, `.../launch/crane_plus_with_peg.launch.py` | peg-in-hole検証で作った棒モデルと起動ファイル（元 table.sdf は無改変） | 要判断 |

退避したい場合は、小さいもの（学習済みモデル・rosbag）を `/workspace`（Mac側 `workspace/`）経由でコピーする。pixi環境（約8GB）は再構築可能なので退避不要。旧ACT/peg-in-holeの詳細な経緯は `.kiro/specs/_backup/final-project-act-peg-in-hole-pre-llm/` を参照。
