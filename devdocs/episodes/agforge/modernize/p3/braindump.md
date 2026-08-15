pj-agdev/agforge/agent/guidesの内容を変えた。
変更に合わせて仕様の方も変えたい。

# やること

## guideの変更確認

guideを変えた。guideに合わせて仕様を変えるので要チェック

## cliツール作成

agforge内部でサブエージェントに渡すビルトインコマンドはなるべく"agforge image generation ..."みたいなcliにまとめる。

agforge toolsets --list ... pj-agdev/agforge/agent/toolsetsの中のtoolset-で始まるファイルの名前と最初に必ず配置される# Descriptionの内容をセットでリストアップ

agforge image generate  ... generate.shから移植
agforge video generate ... プロンプトだけの動画生成、パラメータ設定は今は無し。

agforge外からつかえるようにするかは未定。
とりあえず中で使えればいい。

## create_front関連のワークフロー変更

toolsets.csvが作成されてたら、列挙されたtoolsetを全てtools/に配置

## create_generator関連のワークフロー変更

tools/フォルダ内に複数のtoolsetファイルを受け取る
他、返答を微妙に変えた。
例えば動画作成時に細かいパラメータを指定されたけど、細かいパラメータは指定できませんがいいですかって聞き返すのが望ましい。

runcreate_generatorがtools/を受け取れるよう、Planeのworkコメントにtools一覧を記入しておく必要があるきがする。

## runcreate_generator関連のワークフロー変更

tools/フォルダ内に複数のtoolsetファイルを受け取る

# agforge video generateの中身

pj-agdev/agforge/.local/resources/comfywf/videoにあるワークフローをagpcのcomfyuiに渡す。

# 注意
生成がうまくいかないからといって無闇にguideを書き足さないこと。
迂闊にガイドを増やすとその問題が解決しても別の問題が生じる可能性がある。