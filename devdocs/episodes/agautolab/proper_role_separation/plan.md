# proper role separation — 実装プラン

背景と論点: [discussion.md](discussion.md)。ゴール: autolabエージェントを
リードエンジニアから**仲介役**に戻す。計画と検証基準(gates)の authorship を
コーディングエージェント側へ移し、autolabエージェントは「要望の受け渡し・
サイクル進行・逸脱審査」だけを持つ。

実験環境につき破壊的変更OK・後方互換不要。既存ジョブディレクトリは捨ててよい。
禁止事項は現行 CHARTER の3つのうち **`--dangerously-skip-permissions` 禁止**
(agstudioポリシー)と **secrets を tracked files に書かない** の2つだけ残す。
それ以外の設計判断は実装者の裁量。

## Step 1 — toolbelt に計画フェーズを追加 (`src/agautolab/`)

ジョブを **plan → awaiting_approval → implement** の2フェーズ制にする。

- `job.py`: `gates` の「non-empty 必須」バリデーション(job.py:53-56)を外す。
  gates 未定義 = 計画フェーズから開始、のシグナルに使える。フェーズを
  state.json 側に持つか job.yaml に持つかは裁量(state 推奨: job.yaml は
  人間/エージェントが書く入力、state.json は機械の状態、という現行の区別を
  保てる)。
- `run_once.py build_prompt()` (69-92行): フェーズで分岐。
  - 計画フェーズ: goal(=ユーザー要望そのまま)を渡し、成果物として
    PLAN.md と **gates 提案**(形式は裁量: `proposed_gates.yaml` 等の
    別ファイルが機械可読で楽)を要求するプロンプト。
    現行の "Make the failing gates pass without weakening..." 文は
    実装フェーズ専用に移す。
  - 実装フェーズ: 現行プロンプト + 承認済み PLAN.md を含める。
- 計画イテレーション完了時に状態を `awaiting_approval` にする。
  **ヒント: `AWAITING_APPROVAL` は state.py に既に存在し、run_once.py:254-257
  で「full-auto では auto-pass、将来の semi-auto フックの停止点」として
  実装済み。** auto-pass をやめて素直に exit する(専用 exit code を足すと
  drive/agent 側から扱いやすい。既存: 0/10/20/30)。

## Step 2 — 承認 CLI (`cli.py`)

autolabエージェントが計画を審査した結果を機械に伝える口。

- `autolab approve <job-dir>`: 提案 gates を正式 gates として確定し
  (job.yaml へ書き戻すか state に持つかは裁量)、実装フェーズへ遷移。
- `autolab reject <job-dir> --feedback <file|text>`: フィードバックを
  次の計画イテレーションのプロンプトに含めて計画フェーズを継続。
  ヒント: 既存の NOTES.md 合流機構(build_prompt の notes 引数)に
  相乗りすると新しい伝達経路を作らずに済む。
- `status --json` にフェーズと承認待ちを出す(agentのポーリング先)。

## Step 3 — テスト整備 (`tests/`, `adapters/fake.py`)

- fake adapter に「計画フェーズでは PLAN.md + gates 提案を書く」挙動を
  足し、plan→approve→implement→converged の一連と reject→再計画を
  トークンゼロで通す。既存 test_run_once.py / test_loop.py は新フローに
  合わせて書き換え(後方互換不要なので旧フロー用テストは削除でよい)。
- `uv run pytest` が全緑になったら Step 4 へ。

## Step 4 — 契約ドキュメントの書き換え

- `agent/CHARTER.md`:
  - Rule 3 を反転: 「**実装もテストも書かない**。goal にはミッションの
    要望をほぼそのまま渡す。委譲先が提案した計画と gates を要望に照らして
    審査し、approve/reject する。逸脱・自分に甘い gates を見つけたら
    reject フィードバックで直させる(自分で書き直さない)」。
  - 残す禁止事項: skip-permissions 禁止、secrets の扱い。他は判断に委ねる
    現行の書き方("everything else is your judgment")を維持。
- `AGENT_GUIDE.md`:
  - 「Seeding a job from scratch」の README/テスト執筆手順を削除し、
    「mkdir + job.yaml(goal=要望)+ run-once → awaiting_approval で
    計画を読む → approve/reject」の新手順に置換。
  - 審査の観点を Lessons に追加: 要望とのトレーサビリティ(要望の各文が
    どの gate に対応するか)、gates が自明にパスしないか、検証エンドポイント
    が名指しされているか。agentify で有効だった敵対的視点(RNG注入で
    「ランダムだからテスト不能」という逃げを塞ぐ等)は「自分で書く」から
    「提案に要求する」に言い換えて残す。
- 既知の教訓も反映(agentify report の watch list):
  - 「ループはフォアグラウンドで回す。headless セッションの background
    タスクはセッションと共に死ぬ」を GUIDE の Lessons へ。
  - drive.sh が MISSION.md より古い NOTES の STATUS を信じる欠陥
    (report の driver-side defect)は、このエピソードで無人運転するなら
    mtime 比較の1行で塞いでよい(裁量)。

## Step 5 — 実証: Snake ミッションの A/B

agentify と同一ミッション(browser Snake)を新フローで1回走らせ、比較する。

- 手順は agentify episode と同じ drive.sh 起動。MISSION.md には要望文だけを
  書く(技術契約に翻訳しない)。
- 比較軸: コスト(agentify 実績: agent層 $3.40 / coding層 $0.92、
  管理コスト比 3.7×)、収束イテレーション数、gates の品質(人間レビューで
  agentify の self-authored gates と比較)、autolabエージェントのセッション
  ログに実装詳細への言及がどれだけ減ったか。
- 自己承認リスク(作業者が自分の書いたテストをパスする構図)の検証として、
  agentify と同様に外部 Playwright 監査を1回かける。
- 実運用ヒント: sonnet-5 の小規模webゲームは 1 iteration $0.31–0.48 /
  12–17 turns。gates は npm 依存ゼロの bare `node --test` が最速
  (`node --test test/` のディレクトリ引数は新しめの Node で誤動作する)。

## Step 6 — report.md

このディレクトリに report.md を書く。特に discussion.md の未解決論点
(gate の決定論性、自己承認リスク、既存リポジトリ適用、プライムエージェント
接続)それぞれについて、このエピソードで得た証拠と残課題を明記する。
CHARTER/GUIDE の追加修正が要ればここで確定。

## 実装者への一般アドバイス

- コードの規模感: 変更の本体は run_once.py のフェーズ分岐と cli.py の
  approve/reject で、いずれも小さい。state.json の後方互換を考えなくて
  よいので、State dataclass にフィールドを足すだけでよい。
- stuck/no-progress 判定(run_once.py:142-149)は計画フェーズには
  なじまない(diff が小さくても良い計画はある)。計画フェーズでは
  無効化するか回数上限だけにするのが素直。
- 迷ったら「autolabエージェントが実装詳細を知らなくても回るか?」を
  判断基準にする。プロンプトや CLI の設計がその方向に倒れていれば正解。
