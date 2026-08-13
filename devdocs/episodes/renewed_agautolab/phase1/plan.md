# Phase 1 実装プラン

`braindump.md` を実装に落としたもの。破壊的フェーズなので後方互換は不要。

## 実装者への裁量

設計判断は実装者に委ねる。以下だけ守れば、あとは自由に決めてよい。

- `.local/` の中身をコミットしない、標準出力に出さない。
- gateway の `/status` `/jobs` `/projects` を消さない（agdevworld の assistant が
  `/api/autolab/<node>/…` で proxy している）。`/guide` だけは消してよい。
- agautolab1 ノードへのデプロイは phase1 の範囲外。agstudio ローカルで完結させる。

各ステップ完了後に `phase1/report<N>.md` を書く。失敗も成果物。

## 前提（2026-08-13 実測）

| 依存 | 状態 |
|---|---|
| Plane CE | `http://localhost:8290` 200、`.local/plane-credentials.env` の API キー有効 |
| gitea | `http://agstudio.local:3000` 200、org `autodev`、トークン `agautolab/.local/gitea/autolab-agent.token` |
| Zulip | `https://agstudio.local:8543` 200、bot `autolab-agstudio-bot` (user_id 11) |
| gateway | `:8791` 200（stub） |
| ollama | `http://127.0.0.1:11434/v1`、`qwen3.6:35b-a3b-coding-nvfp4` あり |
| harness | opencode: `~/.local/bin/opencode`、claude_code: `.local/agents.local.toml` の glob で解決 |

`pj-*` チャンネルは既に慣行として存在する（`pj-spike`, `pj-whack-a-mole`）。
gitea の `<name>` + `<name>-direction` 命名も既存（`three-choice-quiz` 他）。

**`agag.harness.run_harness()` は本物が生きている。** stub 化されているのは
agautolab 側の `role_run.py` だけ。

---

## Step 1. 権限を広げる

front ロールが `uv run new_mission.py` を実行できるようにする。

- `agent/opencode-front.json` … `bash` が `agautolab.role_run director *` 以外を
  全 deny している。mediator と同等まで広げる。
- `src/agautolab/role_run.py` の `ROLE_ALLOWED_TOOLS["front"]` … claude_code 側の
  同じ制限。ここも mediator 相当に広げる。

**両方直すこと。** 片方だけだとプロファイルを `local`↔`sonnet` で切り替えたときに
片方でだけ動く、切り分けの面倒な壊れ方をする。deny は必要最小限でよい。
`--dangerously-skip-permissions` は不要（`--allowedTools` で足りる）。

## Step 2. uv workspace 化と front/mediator ワークスペース作成

`agent/front/` と `agent/mediator/` は現状**空ディレクトリ**（git 未追跡）。

- agautolab をルートとする uv workspace にし、`agent/front`・`agent/mediator` を
  メンバーにする。ロックとバージョン解決を1箇所に保つため。
- スクリプトは `agent/front/new_mission.py` のように**ワークスペース直下の実行ファイル**
  として置く。front に渡すプロンプトが `uv run new_mission.py` と書く以上、
  cwd から素直に動く形にする（`uv run -m ...` にするとプロンプト文面も
  二重管理になる）。パッケージ本体を `src/` に置くかは任意。

## Step 3. agag に `topic_dump` / `topic_write` を追加

pyagag（`/Users/eiji/projects/pyagag`、パッケージ `agag`）側の作業。

- `topic_write(topic, text)` … `ZulipClient.send_to_channel()` の薄いラッパ。
  資格情報は `ZulipClient.from_env()` で既に共通化済み。
- `topic_dump(channel, topic, chatlog)` …
  `(cwd)/.local/topics/<channel>/<topic>/<N>/chatlog.txt` に書く。
  N は 1 からの単純インクリメントで、**再発火のたびに増えてよい**
  （会話の版を残すのが目的。冪等でないことを一行コメントで明示すること）。
  完了時に「`.local/topics/…/chatlog.txt` はあなたが参加するチャットのログです」
  相当の英文を返す。失敗は例外。

**ハマりどころ**: `agautolab/pyproject.toml` は pyagag を GitHub の `main` から
取っている。ローカル編集を反映するには一時的に editable 参照
（`../../pyagag`）に切り替えて開発し、最後に GitHub へ push して
`uv lock --upgrade-package pyagag` で戻す。gitea ミラーは黙って古くなるので
参照しないこと。

なお `topic_history()` は既にあるので、ログ取得を作る必要はない。

## Step 4. `role_run.run_role` を `run_harness` に再接続

`src/agautolab/role_run.py` は今、ロールを解決して定型文を返すだけ。
ここが phase1 の実質的な山。

- `agag.harness.run_harness()` に cwd / allowed_tools / opencode_config /
  transcript / timeout を渡して実際にプロセスを起動する。
- `role_run.py` に `_opencode_config()` と `ROLE_ALLOWED_TOOLS` が残っているので、
  配線先はそろっている。`check_available=False` は外す（実際に起動するので
  バイナリが無ければ落ちてよい）。
- front の cwd は `agent/front/`、mediator は `agent/mediator/` に固定。

## Step 5. gateway の `/window` を薄くする、`/guide` を廃止

`agent/gateway.py`。

- `WINDOW_PROMPT` を廃止し、受け取ったテキストをほぼそのまま front に渡す。
  削除済みループ前提の `MISSION_BLOCK` / `apply_mission_block` /
  `start_mission` / `window_state` も一緒に落とす。
- `/guide` ルートと `read_guide()` を削除。`agent/GUIDE.md` は既に削除済み
  （git status の ` D`）。**能力カードは作らない**——front が何をできるかは
  `new_mission.py --help` だけが教える。Evidence Driven のため無から始める。
- 単一入口・排他ロック・400/409/502・run record の永続化はそのまま残す。
- `/guide` の外部消費者がいないことは確認済み（agdevworld の `/api/guide` は
  assistant 自身のカードで無関係）。

## Step 6. `agautolab/init_project.py`

引数はプロジェクト名。各ステップ冪等（既にあればそのまま進行）。

1. Plane プロジェクト作成
2. gitea に `<name>` と `<name>-direction` を作成（org `autodev`）
3. `.local/projects/<name>/main` と `.local/projects/<name>/direction` にクローン
4. 最後まで到達したら `success`

**参考実装**: [autolab-projects.mjs](../../../../agdevworld/assistant/autolab-projects.mjs)
に同じ手順の JavaScript 実装がある。API のエンドポイント・ヘッダ・レスポンス形は
そこから読める。ただし**あちらは冪等でない**（POST が既存で失敗する）ので、
409/422 を「既にある」として飲み込む処理は新規に書く。同じ手順が2言語に
存在することになる点は承知の上。

**Plane identifier**: プロジェクト作成には `identifier`（大文字英数、
ワークスペース内一意、12文字以内）が必須。`.mjs` の `planeIdentifier()` が
「単語の頭文字＋数字部分」で `whack-a-mole` → `WAM` を決定的に生成する規則を
持っているので、これを移植する。衝突したら末尾に数字を足す（`WAM` → `WAM2`）。
identifier は `PA-12` の形で人間が毎日見る issue キーになるのでランダムは避ける。
既存: `Three Choice Quiz`→`PA`, `Whack A Mole`→`WAM`。

**gitea クローン認証**: `.local/gitea/askpass.sh` が
`AUTOLAB_GITEA_TOKEN_VALUE` を読む `GIT_ASKPASS` として使える。
URL にトークンを埋める方法でもよい。

**空リポジトリ**: main 側は初期ファイルなしで作られるのでクローン時に
「empty repository」警告が出るが正常。direction 側は `.mjs` が
`GUIDE.md` / `concept.md` / `.gitignore` を seed していた——今回は
GUIDE.md を作らない方針なので、何を置くか（あるいは何も置かないか）は
実装者判断でよい。

## Step 7. `agent/front/new_mission.py`

引数はミッション名とミッション説明。Plane にタスク（issue）を追加するだけ。
成功したら `success`。

- `--help` が front エージェントにとって唯一のインターフェース仕様になる。
  **簡潔かつ具体的に**書くこと。ここの質がそのまま成功率になる。
- Plane issue 作成は
  `POST /api/v1/workspaces/<slug>/projects/<uuid>/issues/`。
  state id は `.local/plane-credentials.env` にあるが、それは既存 ProjectA の
  もの。新規プロジェクトでは `…/projects/<uuid>/states/` を引いて名前から
  引き当てる（`.mjs` の `stateIdForName()` が同じことをしている）。

## Step 8. `zulip_listener` の差し替え

`src/agautolab/zulip_listener.py`。`accept()`（`mission-` prefix・チャンネル
非依存）はそのまま使える。`handle_message()` を4つのワークフローに置き換える。

1. `topic_dump` を実行
2. `init_project.py` を実行（**存在確認せず毎回**。冪等なので確認より単純で安全）
3. `/window` を呼ぶ。プロンプトは topic_dump の返り値 ＋
   「これを読んでミッションの依頼だと判断したら `uv run new_mission.py --help`
   で使い方を確認し、新しいミッションを追加せよ。完了後に結果を報告せよ」
   相当の英文
4. `/window` の返り値をそのまま `topic_write` に渡す

**急所**: Zulip は **bot が購読していないチャンネルのイベントを配信しない**。
`#pj-新規` を人が手で作っただけでは listener に届かない。
`pj-*` を定期的に探して購読する処理を足すこと。ここが
「チャンネルの存在をプロジェクト開始意思と認める」方針の実装上の要。
（assistant 経由で作った場合は全ユーザーを購読させているので届く。）

## Step 9. 動作確認

新しい `#pj-<名前>` チャンネルを作り、`mission-*` トピックに依頼を書いて、
Plane にタスクが増え、トピックに返信が返るところまで通す。

確認コマンド:

```sh
curl -s http://localhost:8791/healthz
curl -s http://localhost:8290/api/instances/
curl -s -H "Authorization: token $(cat agautolab/.local/gitea/autolab-agent.token)" \
  http://agstudio.local:3000/api/v1/user/repos
```

listener は `agent/zulip_listen.sh`、gateway は
`python3 agent/gateway.py`（`.local/agent/gateway/serve.log`）。

front のプロファイルは既定で `local`（opencode + ollama）。ローカルモデルで
通らないときは `.local/agents.local.toml` か `agents.toml` で `sonnet` に
切り替えて切り分ける——**モデルの問題かプロンプトの問題かを分けること**が
このフェーズで一番効く。

各リポジトリ（agautolab / pyagag）はコミットしたら push する。
