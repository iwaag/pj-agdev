pj-agdev/devdocs/episodes/renewed_agautolabでゼロから作り直したautolabの仕組みがかなり良さそうだ。
agforgeも追従させたい。

ポイントは
1. Zulipによる連携
2. Planeによるタスク管理
3. 短く最小限のプロンプト連結合成とzulipリスナーによるワークスペースビルディング

まずはPlan workの追加から。

# やること

## createトピックの新しいワークフロー作成
まず既存のcreateトピック画像生成の仕組みを改変。

### 共通処理実行(まず返答)

### 固有処理
トピックfrontフォルダ作成
.local/topics/(channel)/(topic)/(N)/front/
Nは単純インクリメントフォルダ

今気づいたがautolabの方にこの(N)のインクリメントフォルダがないので継続チャットで問題が出るはず。後で修正。 

chatlog.mdにチャットログダンプ

上記フォルダ上で
「ワーキングディレクトリにチャットログを配置しました。あなたはチャットログの中の(アカウント名)です。」+pj-agdev/agforge/agent/guides/create_front/guide.mdのプロンプト連結でfrontエージェント起動。

ここまでははautolabのエージェントと全く同じ。
共通化できるコードがあれば共通化。

返事をtopicに投稿、ワークスペース内にrequired_items.mdがあったら

トピックgenerateフォルダ作成
.local/topics/(channel)/(topic)/(N)/generator/

required_items.mdとpj-agdev/agforge/agent/guides/create_generator/tools.mdをここにコピー。

pj-agdev/agforge/agent/guides/create_generator/guide_plan.mdをそのままプロンプトとしてgeneratorエージェント起動。

plan.mdがあった場合はPlane workを追加。idea.mdがあった場合は内容をtopicにそのまま投稿。

なお、Plane workはプロジェクトチャンネルのcreateトピックのときはプロジェクトのworkとして、それ以外はFreeForgeっていうプロジェクトを作ってそこに追加していく形にしたいが、実装重そうなら一旦FreeForgeに集約でもいい。[AUTO]タグはつけない、この問題は後回し。

最後にエージェントの返答を投稿。

## その他

動作テストはsonnet、autolabでの悲劇を繰り返さない。