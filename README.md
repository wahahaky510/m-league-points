# Mリーグ 身内順位（2025-26）

Mリーグの公式成績（[m-league.jp/stats](https://m-league.jp/stats)）を毎週自動でスクレイピングし、
身内メンバーの「担当チーム合計ポイント」でチーム順位・個人順位を集計する。
結果は **Google Sheets**・**LINE（Flexメッセージ）**・**Webダッシュボード（GitHub Pages）** に配信する。

去年の3本のスクリプト（`元/`）を、設定・秘密情報・共通処理を整理した1つのパイプラインに作り直した版。

## 構成

```
config/teams.yaml        担当マッピング（チーム→身内の誰）
src/
  config.py              設定・秘密情報（環境変数）・Google認証
  scraper.py             m-league.jp/stats スクレイピング（成績）
  schedule.py            m-league.jp/games スクレイピング（試合日程）
  standings.py           集計＋JSONスナップショット保存
  sheets.py              「順位表」シート更新
  notify_line.py         LINE Flexメッセージ送信
  dashboard.py           docs/*.html 生成（順位・日程カレンダー・アーカイブ）
  main.py                実行エントリ
data/seasons/<season>/   latest.json / history.json / snapshots/日付.json / schedule.json
docs/index.html          順位ダッシュボード（現シーズン）
docs/calendar.html       試合日程カレンダー（担当チーム色分け）
docs/archive.html        シーズンアーカイブ一覧
docs/season-<season>.html 各シーズンの最終順位
.github/workflows/       週次自動実行
```

## ローカル実行

1. 依存インストール
   ```bash
   pip install -r requirements.txt
   python -m playwright install chromium
   ```
2. `credentials.json`（サービスアカウント鍵）をリポ直下に置く
3. `.env.example` を `.env` にコピーして値を埋める（`LINE_CHANNEL_ACCESS_TOKEN` など）
4. 実行
   ```bash
   python -m src.main --dry-run   # 外部送信なしで確認（集計＋ダッシュボードのみ）
   python -m src.main             # 全部実行（シート更新・LINE送信あり）
   ```

`--no-line` / `--no-sheet` / `--no-dashboard` で個別スキップも可能。

## GitHub Actions（自動化）

2つのワークフローが自動実行する（いずれもレギュラーシーズンの月＝9〜3月のみ）：

| ワークフロー | タイミング(JST) | 内容 |
|---|---|---|
| `.github/workflows/update.yml` | **月・火・木・金 23:00** | 集計・シート更新・共有画像・ダッシュボード更新（LINEは送らない） |
| `.github/workflows/notify.yml` | **土 10:00** | 直近データの個人順位スクショ＋URLをLINEグループへ配信 |

リポジトリの **Settings > Secrets and variables > Actions** に以下を登録する：

| Secret | 中身 |
|---|---|
| `GOOGLE_CREDENTIALS_JSON` | credentials.json の中身を丸ごと貼り付け |
| `SPREADSHEET_ID` | 対象スプレッドシートID |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Messaging API のチャネルアクセストークン |
| `LINE_TARGET_ID` | 送信先の身内グループID |
| `DASHBOARD_URL` | GitHub Pages の公開URL |

## GitHub Pages（ダッシュボード）

**Settings > Pages** で「Deploy from a branch」→ `main` ブランチの `/docs` フォルダを指定する。
`https://<ユーザー名>.github.io/<リポジトリ名>/` で公開される。

## 担当マッピングの変更

シーズン編成が変わったら `config/teams.yaml` の `assignments` を編集するだけ。
`team` は m-league.jp のチーム名と完全一致させること。
