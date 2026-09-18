"""実行エントリ：スクレイピング→集計→保存→シート更新→共有画像→ダッシュボード生成。

集計はレギュラーシーズン（9月〜3月末）のみ。4月以降はセミ/ファイナルなので
成績集計・シート更新を行わず、3月末時点の最終順位を確定として残す。
（日程・ダッシュボードの再生成は行う。--force で強制実行も可能。）

LINE送信はここでは行わない。共有画像を GitHub Pages に公開してから送る必要があるため、
デプロイ後に別ステップ `python -m src.notify_line` で送信する（Actions がその順で実行）。

使い方（リポ直下から）:
  python -m src.main                 # 集計・シート・画像・ダッシュボード
  python -m src.main --no-sheet      # シート更新をスキップ
  python -m src.main --dry-run       # シート更新なし（=--no-sheet）
  python -m src.main --force         # レギュラーシーズン外でも集計を強制実行
"""
from __future__ import annotations

import argparse
import sys

from .config import load_settings
from .scraper import scrape_all_teams


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mリーグポイント争奪戦パイプライン")
    parser.add_argument("--no-sheet", action="store_true", help="シート更新をスキップ")
    parser.add_argument("--no-dashboard", action="store_true", help="ダッシュボード生成をスキップ")
    parser.add_argument("--dry-run", action="store_true",
                        help="シート更新をスキップ（=--no-sheet）")
    parser.add_argument("--force", action="store_true",
                        help="レギュラーシーズン外でも成績集計を強制実行")
    args = parser.parse_args(argv)

    skip_sheet = args.no_sheet or args.dry_run

    settings = load_settings(require_line=False)
    teams_cfg = settings.teams
    regular = teams_cfg.in_regular_season() or args.force

    # 試合日程・結果の収集・保存（レギュラーシーズン分のみ）
    # 既に取得済みの結果は蓄積分として引き継ぎ、新規試合の結果だけ追加する。
    from .schedule import load_schedule, merge_results, save_schedule, scrape_schedule
    try:
        games = scrape_schedule(teams_cfg.season, teams_cfg.regular_season_end_month)
        games = merge_results(games, load_schedule(teams_cfg.season))
        save_schedule(teams_cfg.season, games)
        done = sum(1 for g in games if g.results)
        print(f"日程取得: {len(games)}試合（結果あり {done}試合）")
    except Exception as e:  # 日程取得失敗は致命ではないので続行
        print(f"日程取得スキップ（エラー: {e}）")

    if regular:
        # 1) スクレイピング
        print("① スクレイピング中 ...")
        stats = scrape_all_teams()
        print(f"   {len(stats)} チーム取得")

        # 2) 集計 + スナップショット保存
        from .standings import (
            build_player_ranking,
            build_snapshot,
            save_player_ranking,
            save_snapshot,
        )
        snap = build_snapshot(stats, teams_cfg)
        save_snapshot(snap)
        print(f"② 集計・保存完了（{snap.date}）")
        print(f"   個人1位: {snap.members[0].name} {snap.members[0].point:+.1f}")

        # 2.1) Mリーグ選手個人ランキング
        players = build_player_ranking(stats, teams_cfg)
        save_player_ranking(teams_cfg.season, players)
        if players:
            print(f"   選手1位: {players[0].player}（{players[0].team}）"
                  f" {players[0].point:+.1f}")

        # 3) シート更新
        if not skip_sheet:
            from .sheets import update_standings_sheet
            update_standings_sheet(settings, snap)
        else:
            print("③ シート更新: スキップ")

        # 3.5) LINE用の共有画像（個人順位カード）を生成
        try:
            from .share_image import render_share_image
            render_share_image(snap)
        except Exception as e:
            print(f"   共有画像生成スキップ（{e}）")
    else:
        print(
            f"⏸ レギュラーシーズン外（〜{teams_cfg.regular_season_end}）のため"
            "成績集計・シート・画像はスキップ。3月末時点の順位を最終とします。"
            "（--force で強制実行可）"
        )

    # 4) ダッシュボード生成（保存済みデータから常に再生成）
    if not args.no_dashboard:
        from .dashboard import render
        render()
    else:
        print("④ ダッシュボード: スキップ")

    print("🎉 完了")
    return 0


if __name__ == "__main__":
    sys.exit(main())
