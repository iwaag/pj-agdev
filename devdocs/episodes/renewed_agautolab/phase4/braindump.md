work実行を実装する。

# 実装ステップ

## 前準備

### project作成時に<project name>-devlogというリポジトリの作成とプロジェクトワークスペースへdevlogというフォルダ名でクローン処理を追加する。
現在のmainとdirectionに加えて三つ目のリポジトリとなる。
今回はとりあえず作るだけ。

### project, direction, devlogリポジトリ作成/clone時に".local/"と書いた.gitignoreを追加してcommit/pushする処理を追加。すでに.gitignoreがある場合は".local/"がなければ追加する分岐付き。


### 新しく生成するプロジェクトのdescription先頭に"[AUTO]"、workのラベルに"AUTO"を追加する処理を追加
既存のプロジェクトは手をつけない

## 実行するワーク選出の実装

以下の条件に合致するworkを一つ選出し、プロジェクト名、work名、description、project ID / issue IDを返すnext_work関数を作る

1. プロジェクトのdescriptionの先頭に[AUTO]がある(case insensitive)
2. workのラベルにAUTOがある。(case insensitive)
3. 状態グループがunstarted
4. 配下のsub-workを持たない(sub-workがある場合はそれ自体を実行すると二重実行になってしまうはず。)

実行優先順は

1. 作成日時が古い
2. サブタスクの通し番号が小さい

優先順は後々改善の必要あるだろうが今はこれでいい。

合致するworkがなければNoneを返す。

## 1work実行処理

agautolabのzulipリスナーに"run-"トピックを追加

### 処理内容(共通処理のあと)

0-1. next_work関数を呼び出してNoneが返ったら"no work"と投稿して終了
0-2. .local/workが存在しない、もしくは空であることを確認。もし残っていたら中止して"work dirty"と投稿して終了。
1. next_work関数で特定したプロジェクトのmainリポジトリワークスペースに、workのタイトルとdescriptionを.local/work/work.mdにdump
2. pj-agdev/agautolab/agent/guides/run_coding/guide_run_coding.mdをプロンプトとしてcodingエージェントをmainリポジトリワークスペースで起動。
3. codingエージェントの処理が完了したらPlaneで.local/work/report.mdの内容をworkのコメントとして追加し、さらに.local/work/success.flagがあったらworkをDoneにする。report.がない場合は"no report"で終了
4. 3でresponseをトピックに投稿
5. .local/workを消去。ここまででwork作成後に途中終了した場合も消去。それでも残る場合のことは後で考える。

なお、トピックのチャットログは読まない。最後にautolab以外の誰かが書き込んでいたら実行するだけの単純なトリガー専用トピックのように機能させる。

## zulipのプロジェクトチャンネル作成から最初のミッショントピックという正規の手順でプロジェクトとミッションを作成、想定通りにworkが生成されているか確認

## generalに"run-1"トピックを作りdeveloperとして"run"と書き込んでワークが実行されるか確認する。

- generalは全てのエージェントのlisten対象とする。
- 既存のmission-トピックは親チャンネルが#pj-であることをチェックし、そうでなければ無視。