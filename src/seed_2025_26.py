"""2025-26 シーズンの最終結果をアーカイブに登録する一回限りのシード。

去年の結果は、元スクリプトが更新していた Google スプレッドシート
「チーム合計」シートの最終順位表（A15:D24=チーム / F15:G20=個人）にある。
その確定値をそのまま Snapshot として data/seasons/2025-26/ に書き出す。

メンバー名は今シーズンと揃える（"れ お"→"れお"、"に の"→"にの"）。
※ 去年の担当編成は今年と異なるため、シートに記録された担当をそのまま使う。
"""
from __future__ import annotations

from .standings import MemberStanding, Snapshot, TeamStanding, save_snapshot

SEASON = "2025-26"
# 概算のシーズン終了時期（正確な日付が不明なため年月のみ。必要なら後で修正可）
FINAL_DATE = "2026-05"


def _norm_name(s: str) -> str:
    return "".join(s.split())


# チーム最終順位（シート A15:D24 / point 降順）: (チーム, 略称, 担当, 点数)
_TEAMS = [
    ("EX風林火山", "風林火山", "れお", 697.3),
    ("KONAMI 麻雀格闘倶楽部", "ファイトクラブ", "ゆうま", 691.4),
    ("BEAST X", "ビースト", "まさき", 689.7),
    ("赤坂ドリブンズ", "ドリブンズ", "とかじ", 246.6),
    ("セガサミーフェニックス", "フェニックス", "いつき", 124.2),
    ("TEAM RAIDEN / 雷電", "雷電", "にの", -213.7),
    ("渋谷ABEMAS", "アベマズ", "まさき", -245.9),
    ("U-NEXT Pirates", "パイレーツ", "にの", -622.4),
    ("KADOKAWAサクラナイツ", "サクラナイツ", "ゆうま", -626.7),
    ("EARTH JETS", "ジェッツ", "とかじ", -740.5),
]

# 個人最終順位（シート F15:G20 / point 降順）: (メンバー, 点数)
_MEMBERS = [
    ("れお", 697.3),
    ("まさき", 443.8),
    ("いつき", 124.2),
    ("ゆうま", 64.7),
    ("とかじ", -493.9),
    ("にの", -836.1),
]


def build() -> Snapshot:
    from .config import load_teams_config

    cfg = load_teams_config()
    by_team = {a.team: a for a in cfg.assignments}
    teams = []
    for (t, s, o, p) in _TEAMS:
        a = by_team.get(t)
        teams.append(TeamStanding(
            team=t, short=s, owner=_norm_name(o), point=p,
            color=a.color if a else "#888888",
            top=a.top if a else "",
            main=a.main if a else s,
            games=0,
        ))
    # 担当メンバーごとのチーム一覧
    member_teams: dict[str, list[str]] = {}
    for ts in teams:
        member_teams.setdefault(ts.owner, []).append(ts.team)
    members = [
        MemberStanding(name=_norm_name(n), point=p, teams=member_teams.get(_norm_name(n), []))
        for (n, p) in _MEMBERS
    ]
    return Snapshot(date=FINAL_DATE, season=SEASON, teams=teams, members=members)


if __name__ == "__main__":
    snap = build()
    save_snapshot(snap, set_global_latest=False)  # 現シーズンの最新は壊さない
    print(f"✅ {SEASON} アーカイブ登録完了")
    print(f"   個人優勝: {snap.members[0].name} {snap.members[0].point:+.1f}")
    print(f"   チーム1位: {snap.teams[0].team} {snap.teams[0].point:+.1f}")
