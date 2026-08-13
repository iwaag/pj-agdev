エージェントのワークスペースの管理方針を大きく転換する。

# 新しい方針

## 全サービス共通のzulipリスナーの挙動
イベントをpushではなくpull方式にしたい。
zulipに何らかの投稿が行われると、直ちに、もしくは何らかのタイミングでzulipに参加する全エージェントが以下の条件に当てはまるトピックを検索する。
1. prefix条件に合致
2. unresolved
3. 自分が最後の投稿者ではない。
条件に合致するものが見つからなければclean、また新たな投稿がおこなわれたらDirtyとして再び検索。
これが投稿のたびに行われる。

## 条件に合致するものが見つかった場合の挙動 - 全トピック共通
- 該当するエージェントは直ちに英語で「メッセージを確認しました、返答までお待ちください」と投稿

## 条件に合致するものが見つかった場合の挙動 - missionトピックの挙動
- 以下のディレクトリを作成
agautolab/.local/topics/(channel name)/(topic name)/front/

- ディレクトリ直下に"chatlog.md"を配置、トピックのログをdump
- PlaneにすでにトピックのWorkがあれば"mission.md"に出力、Sub-Workがあれば順に"task[N].md"に出力
- 英語で「ワーキングディレクトリにチャットログを配置しました。あなたはチャットログの中の(アカウント名)です。」、場合によって「現状のミッション、タスクもワーキングディレクトリに配置しました。」という文字列をはさみ、pj-agdev/agautolab/agent/guides/mission_front/guide_mission_topic.mdを連結してプロンプトを作成し、agautolab/.local/topics/(channel name)/(topic name)/front/ディレクトリ上でfrontエージェントを起動して渡す。
(今までは/mission routeを起動していたが変更。)

### windowからレスポンスが帰ってきたとき、ディレクトリ内に"new_mission.md"があった場合
- トピックのworkを更新、既存のサブタスクは全てcancel。
- agautolab/.local/topics/(channel name)/(topic name)/coding/を作成
- 上記codingディレクトリ内に"new_mission.md"をコピーしてcodingエージェントを起動
- pj-agdev/agautolab/agent/guides/mission_coding/guide_task_split.mdをそのままプロンプトとして渡す。
- フォルダ内に"task[N].md"があれば全てトピックworkのsub-workとして登録。


## その他のトピックの挙動

全サービス共通のzulipリスナーの挙動以外は今と同じ。
現時点でcreateトピックしかないはず。

