次は実際の実行。
基本的にはautolabのrun-に近い実装になるはず。
実装は共通化できる部分はしていいが、逆に複雑になるようなら無理はしない。

# やること

## workのラベルに"FORGEAUTO"を追加する処理を追加

## 実行するワーク選出の実装
autolabとの違いはworkのラベルがFORGEAUTOということだけ。FreeForgeのdescriptionには[AUTO]をつけておくことで他のプロジェクトと同じに扱えるはず。

## runcreate-トピックのイベント実装
autolabのrun-トピックとほぼ同じフローだが

1. pj-agdev/agforge/.local/agentws/(work id)/generator/をワークスペースと
2. ワークスペースに、createで渡したのと同じtools.mdと、workのdumpであるplan.mdを置いておく。また"result/"フォルダーと
3. pj-agdev/agforge/agent/guides/runcreate_generator/guide.mdをプロンプトにしてgeneratorを起動する。

というのが違い。
またautolabと違ってworkごとにフォルダをつるので.local/workを作ったり消したりする必要は無く、今はワークスペースは消さずにそのまま残しておいていい。

また追加要件として
1. 生成した後にresultフォルダが空ならgeneratorの返答を元のcreateチャンネルに投稿する、そうでなければ中身をzipにして一時ダウンロードURLを生成して投稿する。

というのを追加。
おそらく元のcreateチャンネルをworkに記録しておく必要がある。commentとして記入しておけばいいかな？

## 動作確認
全てsonnet、FreeForgeとして行う。