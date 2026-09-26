# 作業記録

このファイルに作業内容を日付ごとに記録してください。

## 書き方
```
## YYYY-MM-DD
- [部署名] 作業内容
```

---

## 2026-09-26
- [開発部] 個人順位の各メンバー名の横に担当チーム名（略称）を小さく表示（_member_rows_html に short_by_team を渡し、snap.teams から生成。複数担当は「・」区切り）。リモートの自動更新(2026-09-25)とdocs競合→コード=自版/データ=リモート最新でマージし、docsを新コードで再生成して解決・push。自動運用(週次update)が本番稼働していることを確認

## 2026-09-18
- [企画部] 去年のMリーグ得点集計スクリプト（元/M-league_stats.py・message.py・image-message.py）をレビュー。トークンのベタ書き・行番号/座標依存・手動実行・3ファイル分散などの課題を整理し、今年版の方針を決定（GitHub Actions週次自動化／LINE Flexリッチ通知／担当表はリポ内YAML／Google Sheets中心継続／GitHub Pagesダッシュボード）
- [開発部] リポ土台を新規作成：config/teams.yaml（担当マッピング）、src/config.py（設定・秘密情報を環境変数へ一元化＋Google認証ヘルパー）、.gitignore、requirements.txt、.env.example、src/__init__.py
- [開発部] src/scraper.py を新規作成。去年のスクレイピング部を TeamStats データ構造で切り出し、m-league.jp/stats を実サイトで動作確認（10チーム・各4選手・18指標取得OK）
- [開発部] 実データに合わせ teams.yaml を修正（合計ラベルを "ポイント" に、チーム名を2026-09時点のサイト表記へ）
- [開発部] credentials.json（元/にあったサービスアカウント鍵）をリポ直下へ配置＋.gitignore済み。Google Sheets認証・読み取りを実スプレッドシートで確認（シート: 選手成績/チーム合計/試合結果/選手情報）
- [開発部] 去年のチーム合計シートB/C列から実際の担当メンバー（とかじ/れ お/ゆうま/まさき/いつき/に の）とチーム割当・略称を teams.yaml へ移植。config.py の Assignment に short 追加
- [開発部] src/standings.py を新規作成。チーム順位＋個人（担当）順位を集計し、data/snapshots/日付.json・latest.json・history.json に保存する仕組みを実装。スクレイピング→集計→保存をライブデータで動作確認
- [企画部] 2025-26シーズンの実編成をユーザーから受領し teams.yaml を更新（にの:ジェッツ/アベマズ、まさき:風林火山、とかじ:ファイトクラブ/ドリブンズ、ゆうま:サクラナイツ/雷電、れお:フェニックス、いつき:ビースト/パイレーツ）
- [開発部] src/notify_line.py を新規作成。去年のテキスト＋座標スクショ2本を廃し、LINE Flexメッセージ1発で個人順位・チーム順位＋ダッシュボードボタンをリッチ表示（構造・サイズ検証OK）
- [開発部] src/dashboard.py を新規作成。latest.json/history.json から docs/index.html（順位表＋Chart.js推移グラフ、ダークテーマ・レスポンシブ）を生成。ブラウザ表示確認OK
- [開発部] src/sheets.py を新規作成。行番号ベタ書き/XLOOKUPを廃し、専用「順位表」シートを毎回クリーン描画する方式に組み直し（他シート非干渉）
- [開発部] src/main.py（--dry-run/--no-line/--no-sheet/--no-dashboard 対応の実行エントリ）、.github/workflows/weekly.yml（週次自動＋手動実行、Secrets運用、data/docs自動コミット）、README.md を作成。--dry-runで通し動作確認OK
- [QA部] ライブスクレイピング10チーム取得・集計・スナップショット保存・ダッシュボード生成・Flex構造/サイズ検証を確認。※実LINE送信・実シート書き込みはユーザー許可待ち（外部送信のため未実行）
- [開発部] シーズン別対応：得点をシーズンごとに独立集計するよう standings.py の保存層を data/seasons/<season>/ 配下に再構成（list_seasons/load_season_latest/load_season_history 追加）。data/latest.json は現シーズン最新を指す
- [開発部] dashboard.py を刷新：index.html は現シーズンのみ表示、season-<season>.html を各シーズン分生成、archive.html でシーズン一覧（優勝者バッジ付き）＋上部ナビでシーズン切替。テンプレートを__KEY__プレースホルダ置換方式にしCSS/JSの波括弧衝突を解消。ブラウザで index/archive 表示確認OK
- [開発部] 試合日程機能を追加。src/schedule.py で m-league.jp/games を月タブ総なめでスクレイピング（クリックでDOM再描画→ハンドル無効化する挙動に対応し、月ラベルを都度取り直してクリック）。150試合（9月〜3月）取得、消化済みフラグ・対戦4チームを data/seasons/<season>/schedule.json に保存。main.py に組込み（失敗は非致命で続行）
- [開発部] シーズン名の誤りを修正：現シーズンは 2026-27（今日=2026-09開始）。去年のシート実データ2025-26に引きずられ誤っていた。teams.yaml を 2026-27 に修正し、誤ラベルの data/seasons/2025-26 と docs/season-2025-26.html を削除して再生成（日程 2026-09-14〜2027-03-02）
- [企画部] タイトルを「身内順位」→「Mリーグ ポイント争奪戦」に変更（dashboard/notify_line/sheets/main 全体、LINE通知・タブ名・シート見出しも）
- [開発部] 去年(2025-26)の最終結果をアーカイブ登録。データは元スクリプトの更新先Googleスプレッドシート「チーム合計」最終順位表(A15:D24/F15:G20)から取得し、去年の担当編成のまま src/seed_2025_26.py にシード化（個人優勝れお+697.3・チーム1位EX風林火山）。メンバー名は今季表記に正規化。save_snapshot に set_global_latest 引数を追加し、過去シーズン投入で現シーズンの latest.json を壊さないよう修正。アーカイブ2シーズン表示をブラウザ確認。※最終日付は不明のため暫定 2026-05
- [企画部] 集計対象をレギュラーシーズン（9月〜3月末）のみに限定する方針を確定（毎年共通、4月以降のセミ/ファイナルは対象外）
- [開発部] teams.yaml に regular_season_end_month=3 を追加。config.py の TeamsConfig に start_year/regular_season_end/in_regular_season/in_regular_season_month を実装。schedule.py で4・5月の試合を除外。main.py をシーズン外は成績集計・シート・LINEをスキップ（3月末順位を最終確定）、日程・ダッシュボードは再生成する構成に変更（--force で強制実行可）。weekly.yml の cron を 9-12,1-3月のみに限定
- [企画部] 確認対応：LINEはグループpushで全員に表示される旨を確認。スマホ表示の整備・Mリーグ選手個人ランキング追加・ナビのアクティブ表示バグ・LINEをスクショ＋URL方式に変更、を依頼受領
- [企画部] 過去シーズンはアーカイブからのみ参照する方針（ナビの年度タブ廃止）。チームランキングをMリーグ放送画面風の見た目に、チームカラーは公式放送準拠に、を依頼受領
- [開発部] ナビから過去シーズンの年度タブを削除（今シーズン/選手/日程/アーカイブのみ）
- [開発部] チームカラー対応：teams.yaml の各チームに color/top/main と games_total(120) を追加。config.py の Assignment・TeamsConfig、standings.py の TeamStanding に反映し、build_snapshot で試合数(=選手の試合数合計)も集計。seed_2025_26 もカラー付与
- [開発部] チームランキングをMリーグ放送風UIに刷新（dashboard._team_broadcast_html）。順位カラースクエア＋チームカラーの横グラデバー＋小/大ラベル＋トータルポイント＋ポイント差(上位との差)＋試合数/120＋前回比▲▼。index/アーカイブを2カラムから縦積み(個人順位→チームランキング→推移グラフ)に変更。PC/スマホ表示確認OK
- [開発部] ナビのアクティブ表示バグ修正：_nav_html を active キー（current/calendar/players/archive/season名）方式にし、各ページで該当タブのみ青くなるよう修正。ナビに「🎴選手」タブ追加
- [開発部] Mリーグ選手個人ランキングを追加。standings.py に PlayerStanding＋build_player_ranking/save/load を実装（全40選手をポイント降順、身内担当を色分け表示）。main.py で集計・保存、dashboard.py の render_players で docs/players.html を生成。スマホ幅で表示確認OK
- [開発部] スマホ表示（375px）で index/players/calendar を確認し、1カラム・ナビ折返し・チップ調整が機能することを確認
- [開発部] LINE通知をFlexからスクショPNG＋URL方式へ全面変更。share_image.py で個人順位カードをPlaywrightで640px×2倍でPNG化し docs/line/standings-<date>.png に出力（Pagesで公開）。notify_line.py を画像メッセージ＋テキスト(ダッシュボードURL)方式に書き換え、公開URLの反映待ちポーリング＋実行エントリを実装。main.py はLINE送信を分離し画像生成まで担当、weekly.yml を「集計→push(デプロイ)→画像公開待ちしてLINE送信」の3段構成に変更。.gitignore で docs/line/*.png を許可
- [企画部] 実行スケジュールを確定：結果更新=月火木金23:00(JST)、LINE配信=土10:00(JST)、いずれもレギュラーシーズンの月のみ
- [開発部] 統合ワークフロー weekly.yml を廃止し2分割。update.yml（cron "0 14 * 9-12,1-3 1,2,4,5"＝JST月火木金23:00：集計・シート・画像・ダッシュボード更新＋push、LINEなし）、notify.yml（cron "0 1 * 9-12,1-3 6"＝JST土10:00：保存済み最新データでLINE画像＋URL配信、スクレイピング/ブラウザ導入なし）。READMEのスケジュール表を更新
- [開発部] UI/文言調整（ユーザー要望）：①推移グラフをタップ開閉式に（onClickでツールチップtrue/false切替、2度目で非表示）②個人順位見出しの「（担当合計）」削除（dashboard/share_image/sheets）③個人順位の下位2名を「雑魚」「クソ雑魚」表記に（_rank_label、ダッシュボード＋共有画像）④日程モーダルの「担当:」プレフィックス削除（担当者名のみ表示）⑤LINEメッセージをFlex化（画像＋トップ/雑魚/クソ雑魚＋Dashboardリンクボタン、日付は9/18形式でISO自動リンク回避）。URLはユーザー名が残る仕様のため現状維持。push済み
- [開発部] 本番デプロイ実施。秘密保護（.gitignoreに元/追加、.env.exampleの実IDをプレースホルダ化）→ git init/commit → gh CLIをwinget導入 → 公開リポジトリ wahahaky510/m-league-points 作成・push → GitHub Pages有効化(main /docs) → 非機密Secrets(SPREADSHEET_ID/LINE_TARGET_ID/DASHBOARD_URL)登録。機密2件(GOOGLE_CREDENTIALS_JSON/LINE_CHANNEL_ACCESS_TOKEN)はユーザーが登録。update-standings初回実行成功（シート更新・画像・ダッシュボード生成、Pages公開200確認）
- [開発部] notify_line にメッセージ先頭ラベル(LINE_MESSAGE_PREFIX)対応を追加、notify.yml に workflow_dispatch入力 note を追加（テスト送信ラベル用）。テスト送信は当初 LINE 401 が続いたが、原因はPowerShell隠し入力へのトークン貼付時の文字欠け。Get-Clipboard経由での再登録で解決し、テスト送信（🧪 テスト送信ラベル付き）成功。これで本番デプロイ完了（更新=月火木金23時／LINE配信=土10時の全自動運用開始）
- [企画部] U-NEXT Pirates の担当を いつき→やはぎ に変更（やはぎを新メンバー追加、いつきはBEAST Xのみ）。teams.yaml 更新、_MEMBER_COLORS を7色に拡張、2026-27再集計＋共有画像・ダッシュボード再生成。個人順位は7人に（3位やはぎ+58.5）。2025-26アーカイブは当時の担当のまま
- [開発部] チームカラーをユーザー指定の公式色10色に修正（teams.yaml：フェニックスdd6b03/JETS04431f/Pirates0e027d/風林火山a70008/雷電e59b19/ABEMASa86406/サクラナイツdf4385/BEAST024958/麻雀格闘倶楽部e50104/ドリブンズ95c500）。保存済みスナップショットにも色が入るため2026-27再集計・2025-26再シード後に全再生成。放送風ランキング/カレンダー/モーダル/凡例へ反映確認
- [開発部] 去年(2025-26)の日程・結果をスプレッドシート「試合結果」タブから取り込み。src/seed_2025_26_schedule.py で試合ごと・回戦ごとの着順/選手/チーム/得点をパース（選手とチームは同列ペアで対応付けし着順ズレを回避）、レギュラーシーズン(9〜3月)に絞り150試合を data/seasons/2025-26/schedule.json に保存。選手→チーム対応の players.json も生成し結果モーダルの色分けを有効化。ゼロサム一致・モーダル表示を確認。これにより日程ページのシーズン選択が2026-27/2025-26で機能
- [開発部] 日程ページにシーズン選択を追加。schedule.seasons_with_schedule() で日程データを持つシーズンを列挙し、render_calendar を任意シーズン対応に（現シーズン=calendar.html、他=calendar-<season>.html）。上部にシーズン切替ピル（2つ以上で表示）。ダミー2季で切替表示・遷移を確認後クリーン化。※サイトは現シーズンの日程のみ提供のため現状2026-27のみ、以降シーズンが貯まると自動で選択肢が増える
- [開発部] 試合結果を蓄積方式に。schedule.merge_results で保存済み schedule.json の結果を新規スクレイプに引き継ぎ、一度取得した最終結果はサイトが古いモーダルを落としても失わないようにした（main.py で scrape→merge→save）。閲覧は元々GitHub Pages上の静的データ参照でライブ取得なし＝軽量、を確認
- [開発部] 消化済み試合の結果表示を追加。schedule.py で各試合の結果モーダル(.c-modal2 id=js-modal-key日付-番号)から回戦ごとの選手名＋得点(▲=マイナス)を抽出し Game.key/Game.results に格納（page.evaluateで一括取得、クリック不要）。dashboard の日付モーダルに、消化済み試合は第1/第2回戦の順位・選手・所属チーム(色)・得点(緑/赤)を表示。選手→チーム色は players.json から名前(空白除去)で突合。動作確認OK（9/14でゼロサム一致を確認）
- [開発部] カレンダーの日付タップで拡大モーダルを追加。セルにdata-date/role=button/tabindexを付与し、CAL_DATA(teams/days)をJSON埋め込み。タップ/Enter/Spaceで対戦カードを拡大表示（日付+曜日、第1/第2試合ごとにチームカラースウォッチ＋フルチーム名＋担当メンバー、消化済み表示）。背景クリック/✕/Escで閉じる。PC/スマホ動作確認OK
- [開発部] カレンダーの1日2試合表示を改善。各試合をチームカラーの2×2タイルにまとめ、複数試合日は「第1試合/第2試合」で区切って表示（旧: 8チップがflex折返しで密集）。チームカラー(teams.yaml)をタイルに反映し、各タイル右に担当メンバー名を付与。凡例を全10チームのカラータイル+担当者名に刷新（色↔チーム対応が一目で分かる）。全チーム担当済みのため白枠(身内)表現は廃止。PC/スマホ確認OK
- [開発部] dashboard.py に日程カレンダー生成 render_calendar を追加。docs/calendar.html に月別カレンダーグリッドを出力し、身内担当チームを担当者色で色分け＋略称表示、消化済みは✓＋淡色、凡例付き。ナビに「📅日程」追加。日程ページと成績ページのチーム名の空白差（KONAMI 麻雀格闘倶楽部 vs KONAMI麻雀格闘倶楽部）を空白除去キーで突き合わせて解決。ブラウザ表示確認OK
