# director_workspace — plan

braindump2.txt の実装計画。既存のdirector機構を白紙に戻し、「本当の最低限の
エージェントワークスペース」から再スタートする。実行者はOmni Agent。
コーディングエージェントとの連携は今回考えない。破壊的フェーズであり後方互換は不要。

## 禁止事項(最小限)

1. agforge・othello-web・executorのコードには手を入れない(削除対象はdirector関連のみ)。
2. token・パスワード類をgit追跡ファイルに書かない(従来どおり`.local/`のみ)。
3. プロセスをkillするときはlsofで特定したPIDに対して行う(pkillのパターンマッチ禁止。
   P3で`pkill -f "python3 window.py"`がmacOSのargv書き換えで空振りし、偽実験を3回生んだ)。

それ以外の実装判断(ルーティング名、関数構成、テストの粒度、コミット分割など)は実装者の裁量。

## Step 0 — 既存director実装の削除

- :8094で旧director windowが**現在も稼働中**。`lsof -nP -iTCP:8094 -sTCP:LISTEN`でPIDを
  取って停止する。:8092(agforge)と:11434(ollama)はStep 4で使うので残す。
- `pj-agdev/director/` をディレクトリごと削除(director.py / window.py / reconcile.py /
  GUIDE.md / README.md / tests / __pycache__)。
- `pj-agdev/.local/.env` の `DIRECTOR_*` キーを削除(gitignore下なので任意だが、残すと
  次の実装が拾う事故のもと)。
- ドキュメント追従: `/Users/eiji/projects/understand_agents.md` のdirector項を
  「白紙化して最小ワークスペースから再構築中(このエピソード参照)」に書き換え。
  `pj-agdev/.local/devenv.md` にdirector関連の記述があれば同様に。
- 旧データ `pj-agdev/.local/asset-reconcile/othello-direction/`(records/candidates含む)は
  歴史的証拠としてそのまま残す。othello-webのmanifestも触らない。
- pj-agdevはgitリポジトリ。削除をコミットしてよい(後方互換不要)。

## Step 1 — giteaに空のディレクション資料リポジトリを作成

- gitea: `http://agstudio.local:3000`(稼働確認済み、v1.27.1)。
- 全ノード共通のデフォルトAI用ユーザー = **autolab-agent**(既存)。
  token: `pj-agdev/agautolab/.local/gitea/autolab-agent.token`。
  API・push手順の実績は `agautolab/devenv/gitea/SETUP.md` にある。
  push URL形式: `http://autolab-agent:<token>@agstudio.local:3000/autodev/<repo>.git`
- リポジトリは `autodev` org配下に作成。**注意**: orgには昨日(2026-08-08)作られた
  空の`director`リポジトリと、中身入りの`gallery-direction`が既に存在する(前実験の遺物)。
  混同を避けるため新規に別名で作ることを推奨(例: `scifi-direction`)。遺物は触らず放置。

## Step 2 — 初期3ファイルを配置してpush

ローカルのclone先はautolabノードの管理下が自然(例: `agautolab/.local/direction/<repo>/`)。
配置場所は裁量だが、Step 3のwindowが参照するパスなので設定値として一元化すること。

1. `.gitignore` — 中身は `.local` の1行のみ。
2. `GUIDE.md` — このエピソードディレクトリに**ユーザーが用意済み**
   (`devdocs/episodes/agautolab/director_workspace/GUIDE.md`)。**一字一句そのままコピー**
   すること。"foder"という綴りや全角スペースが含まれるが、ユーザー原文なので修正しない。
3. `concept.md` — 中身は次の1行:
   `This is Scifi-themed game. All images must follow futuristic aesthetics.`

コミットしてgiteaへpush。

## Step 3 — autolabにdirector用の単一window(テキストin/out)を設置

- 設置先は `agautolab/agent/gateway.py`(:8791)。既存の `POST /window` 一式
  (649行目付近〜: 記録の連番書き出し、in-processロック、WindowErrorの流儀)が
  そのまま雛形になる。ルート名は裁量(例: `POST /director`)。
- 動作: エージェントCLIワンショット。入力文字列を
  `First, read GUIDE.md. Then, follow this request.:\n` + text
  に連結して渡し、返答テキストをそのまま返す。
- **バックエンドはclaude一択**(`claude -p`、cwd=Step 2のclone)。理由:
  - ワークスペースのファイルを自力で読めることが実験の前提(GUIDE.mdを読む指示、
    concept.mdを勝手に読むかの観察、Test 3の画像review)。ollamaはツールを持てない。
  - 既存windowのclaudeバックエンド(gateway.py 808行目付近)は**意図的にツール無し**で
    起動している。ここを流用する場合、ツール許可(最低 Read,Glob,Grep)を付けること。
    許可しないと実験全体が成立しない。
- **プロンプトにGUIDE.md/concept.mdの内容を注入しない**こと。braindump 3-2の観察
  (言及していないconcept.mdを自発的に読むか)が今回の主要な実験対象。
  システムプロンプト相当の飾りも足さず、上記の連結文字列だけを渡す。
- claudeバイナリ解決の罠: バージョン番号入りの拡張ディレクトリへの絶対パス指定は
  更新のたびに死ぬ(autolab×2、agforge×1、P3×1の実績)。PATHの`claude`か、
  glob解決を使うこと。
- 記録: 既存windowと同じ`run-NNNN.json`パターンで残すのが安い(Phase 1記録方針)。
- 画像reviewはP3実測で9〜30秒かかった。既存の`WINDOW_TIMEOUT_SECONDS=120`は
  そのままで足りる見込み。

## Step 4 — 入力テスト(window経由)

すべて設置したwindowへのPOSTで行い、返答と記録を保存する。

1. **Test 1**: `What is this project?`
   - 観察点: 返答にScifi要素が現れるか = concept.mdを自発的に読んだかの判定材料。
     判定を確実にしたいなら、同じプロンプトを手元で
     `claude -p --output-format stream-json` により実行してツール呼び出し列を見る手もある
     (windowの実装を汚さないこと)。
2. **Test 2**: `Suggest prompt to generate background image of this game.`
3. 返答のプロンプトを使ってagforge(:8092、稼働中)で画像を実生成。
   APIは `agforge/service/charter.md` 参照。
   既知の癖: agforgeは1回目はPNGを返すが、リトライ時はJPEGを返しがち(P3観察)。
4. 生成画像をdirectorワークスペースの `.local/image/background.png` に配置。
   braindump原文は`background.md`だが画像なので`.png`が妥当(逸脱としてreportに記録)。
   `.gitignore`により`.local`はpushされない——これは意図どおり。
5. **Test 3**: `review .local/image/background.png` と質問。
   - 観察点: concept.mdの"futuristic aesthetics"を判断基準として持ち出すか。
     claudeのReadは画像を読める。

コスト見込み(P3実測ベース): window応答1回0.09〜0.26 USD、画像review 0.13〜0.18 USD。
テスト一式で1 USD前後。

## Step 5 — 記録と報告

- このディレクトリに `report.md`。最低限入れるもの:
  - 各テストの入出力(要約でよいが、concept.mdを読んだか否かの判定は根拠つきで)
  - braindumpからの逸脱(`.png`の件、リポジトリ名など)と理由
  - 次に足したくなった要素(このエピソードの目的は「必要な要素をテスト運用から
    発見する」ことなので、これが本体)
- devpolicy/policy.mdのDeus Ex Machina記録: 今回はOmni Agentがautolab・director両域を
  直接操作するので、介入として記録する。
- pj-agdev(gateway.py改修、ドキュメント、エピソード資料)をコミット。

## 実装者への参考情報(拘束ではない)

- gateway.pyのwindow機構は記録・ロック・バックエンド切替が整っていて、director窓は
  その縮小コピーで足りる。ただし旧director.pyのような文脈組み立て(ファイル連結、
  manifest注入、VERDICT契約)は**今回のスコープ外**。「読めと言われたら自分で読む」が
  今回の設計思想であり、ハーネスが賢くなることは実験を汚す。
- 旧実装で唯一持ち越す価値があるのは実装の教訓のみ: claudeパス解決のglob、
  記録はどんな失敗でも書く、`-p --output-format json`の`is_error`/`total_cost_usd`の読み方
  (`agautolab/src/agautolab/adapters/claude_code.py` に同じ処理があり、これは残る)。
- サービス再起動後は必ずPIDで新旧を確認する(healthcheckは版を教えてくれない)。
