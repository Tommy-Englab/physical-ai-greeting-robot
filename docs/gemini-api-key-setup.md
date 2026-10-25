# Gemini APIキーの取得と設定（Task 1 の前提・ユーザー作業）

> B案のLLMは Google Gemini（無料枠）を使う。このキー発行と設定は**ユーザーの作業**。キー値はチャット・コード・spec・commitへ絶対に貼らない。`.secrets/` または環境変数で管理する。
> 手順は 2026-10-11 時点の公式情報に基づく。画面やモデル名は変わりやすいので、実際の作業時に公式ページで最新を確認する。

## 0. 前提と注意

- 無料枠で足りる見込み（本案は「短い自然言語→小さなJSON」で軽量）。課金設定（billing）は必須ではない。
- **認証キーの移行に注意**: Gemini API は認証方式が更新され、古い形式のキーは将来拒否される告知がある。**いま新規に発行したキー**を使えば問題ない。古いキーを使い回さず、新しく作る。
- キーは「サーバー側の秘密」として扱う。ブラウザやモバイルのコードに埋め込まない（本案はコンテナ内Pythonで使うので該当しない）。

## 1. APIキーを発行する（ユーザー作業）

1. ブラウザで Google AI Studio を開く（`https://aistudio.google.com` または `https://ai.dev`）。
2. 自分の Google アカウントでサインインし、利用規約に同意する。
   - 新規ユーザーは、既定の Google Cloud プロジェクトとAPIキーが自動作成されることがある。
3. 左下または左サイドバーの「Get API key / APIキーを取得」を開く（直接 `https://aistudio.google.com/app/apikey`）。
4. 「Create API key / APIキーを作成」を押し、キーを発行する。
5. 発行されたキー文字列をコピーする。**この値はチャットに貼らない。** 次節で直接 `.secrets/` に書く。

参照（確認日 2026-10-11、内容は要約・言い換え）:
- Gemini APIキー: https://ai.google.dev/gemini-api/docs/api-key
- はじめに: https://ai.google.dev/gemini-api/docs/get-started

## 2. キーを設定する（Mac側に置きコンテナへコピー・ユーザー作業）

方針: **キーの正本はMac側リポジトリの `.secrets/gemini.env` に置き、そこからコンテナへコピーして使う。** 本プロジェクトは `.gitignore` で `.secrets/`・`.env`・`*.env` を除外済みで、`.secrets/` 配下はgitに乗らない（空ファイルで検証済み）。Mac側に置けばコンテナを `docker rm` しても消えず、再作成時はコピーし直すだけで済む。

### 2.1 Mac側に秘密ファイルを作る（正本）

Macのこのリポジトリ直下で作る。`<発行したキー>` を実際の値に置き換える（ユーザー自身が行い、値は共有しない）。`.secrets/` ディレクトリは作成済み。

```bash
# リポジトリ直下（このリポジトリをcloneしたディレクトリ）で
printf 'GEMINI_API_KEY=%s\n' '<発行したキー>' > .secrets/gemini.env
chmod 600 .secrets/gemini.env

# gitに乗らないことを確認（何も出なければOK）
git status --short | grep secrets || echo "OK: .secrets はgit管理外"
```

### 2.2 コンテナへコピーする

コンテナ `pai_ros2` が起動している状態で、Macから `docker cp` でコンテナのホームへ置く。

```bash
docker cp .secrets/gemini.env pai_ros2:/home/ubuntu/gemini.env
```

> `/workspace` マウント経由でも渡せるが、`docker cp` が最も単純。コピー先はコンテナ内 `~/gemini.env`。

### 2.3 コンテナ内で読み込む

コンテナ内（ブラウザのTerminator）で、推論を試す前に読み込む。ROS 2 を使うシェルと同じターミナルでよい。

```bash
set -a; source ~/gemini.env; set +a
# 確認（値そのものは表示しない。設定されているかだけ見る）
test -n "$GEMINI_API_KEY" && echo "GEMINI_API_KEY is set" || echo "NOT set"
```

> 注意: `echo $GEMINI_API_KEY` のように値を画面へ出さない（録画・スクショ時の漏洩防止）。設定済みかは上記の `test -n` で確認する。
> コンテナを作り直したら 2.2 のコピーからやり直す（Mac側の正本は残っている）。

## 3. 疎通の最小確認（Task 1 で Kiro が用意するコードで実施）

キー設定後、Task 1 で次を順に確認する（撤退判断ゲート。1〜2時間以内に通らなければ継続可否を再判断）。

1. コンテナから Gemini の公式HTTPS endpoint へ接続できる。
2. 最小のテキスト推論が1回成功する（status・所要時間を記録、キー値は記録しない）。
3. 「お辞儀して」から、確定済みschema（`docs/preset-and-schema-design.md` 3節）に準拠する `bow` 計画JSONが得られ、validator単体で合格する。

接続テスト用の最小コードと検証コードの枠組みは Kiro が用意する（SDKは google-genai、構造化出力を使う）。

## 4. やってはいけないこと

- キー値をチャット・README・spec・ログ・commit・動画・スクショに出さない。
- `.secrets/` を git に追加しない（`.gitignore` 済み。`git add -f` などで強制追加しない）。
- 公開リポジトリに上げる前に、過去コミットもキー混入が無いか点検する。
