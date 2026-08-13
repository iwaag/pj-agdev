次はミッション分割を行う。

# 方針
missionトピックを受信した時のアクションに、ミッション分割を加える。
Planeのsub-workとしてミッションを分割する。
内容はdescriptionに記入する。
本来はcodingエージェントとdirectorエージェントの連携で作らせたいが今回はcodingに全てやらせる。
動作テストは全てsonnet。コストは無制限。

# 実装ステップ

## プロンプト合成方式変更

- ハードコーディングされている合成プロンプトを削除。pj-agdev/agautolab/agent/guides/front/guide_mission_topic.md読み込みで置き換え。(window_prompt())

## new_mission.pyの変更とzulip_listenerでの実行に変更
- new_mission.pyはchatlog dumpのフォルダに追加されたmission.mdでPlaneタスク作成、tasks/[N].mdでsub work作成という仕様に変更
- front missionに英語で「(chatlogのディレクトリのパス)はあなたの参加するチャットのログです」＋(pj-agdev/agautolab/agent/guides/front/guide_mission_topic.md)の合成プロンプトで起動。
- codingエージェントをfrontエージェントのワークスペースで起動して、英語で「(missio.mdの相対パス)はミッションを記したファイルです。」+ (pj-agdev/agautolab/agent/guides/coding/guide_task_split.md)という合成プロンプトで起動。codingエージェントをfrontエージェントのディレクトリで起動している点については今回は気にしないで。
- 実行タイミングは、/windowsでエージェントの返答後にzulip_listenerのコードから実行するように変更。返答内容はチェックしない。二重作成を防止するため方法が必要、追加済みマークか何かが必要かもしれない。

## Omniエージェントによるワークフローチェック
- OmniエージェントがZulip_listeenrのトリガーもIn-Systemエージェントも介さずに新規プロジェクト作成からnew_mission.pyによるsub work付きタスクの作成を

## autolabエージェントによるワークフローチェック(sonnet固定)


## localエージェントで追試。localエージェントはトラブルが多いので深入りしないこと。
