"""2025-26 シーズンの試合日程・結果を、スプレッドシート「試合結果」から取り込む。

去年の結果は元スクリプトの更新先スプレッドシートの「試合結果」タブに、
試合ごと・回戦ごとの着順/選手/チーム/得点として入っている。それを
今季と同じ Game/results 形式に変換し、data/seasons/2025-26/ に保存する。

集計対象はレギュラーシーズン（9〜3月）のみ（4〜5月のセミ/ファイナルは除外）。
選手→チームの対応（players.json）も作り、結果モーダルの色分けに使う。
"""
from __future__ import annotations

from datetime import date

from .config import build_google_credentials, load_settings, load_teams_config
from .schedule import Game, _parse_point, save_schedule
from .standings import PlayerStanding, save_player_ranking

SEASON = "2025-26"
START_YEAR = 2025
SHEET = "試合結果"
_WD = ["月", "火", "水", "木", "金", "土", "日"]


def _iso(mmdd: str) -> str | None:
    try:
        mm, dd = mmdd.split("/")
        m, d = int(mm), int(dd)
    except (ValueError, AttributeError):
        return None
    year = START_YEAR if m >= 9 else START_YEAR + 1
    return date(year, m, d).isoformat()


def _pad(row: list, n: int = 11) -> list:
    return list(row) + [""] * (n - len(row))


def _read_rows() -> list[list]:
    s = load_settings(require_line=False)
    from googleapiclient.discovery import build
    creds = build_google_credentials(
        s, ["https://www.googleapis.com/auth/spreadsheets.readonly"])
    svc = build("sheets", "v4", credentials=creds)
    r = svc.spreadsheets().values().get(
        spreadsheetId=s.spreadsheet_id, range=f"{SHEET}!A1:K2000").execute()
    return r.get("values", [])


def parse_raw(rows: list[list], regular_end_month: int = 3) -> list[dict]:
    """試合ごとに {date, teams, rounds:[{round, scores:[(name, point, team)]}]}。

    各回戦は着順順に並ぶため、選手とチームは同じ列ペア(row[c], row[c+1])から
    正しく取得する（回戦ごとに着順が変わっても対応がズレない）。
    """
    games: list[dict] = []
    cur: dict | None = None
    i = 1  # 1行目はヘッダ
    while i < len(rows):
        row = _pad(rows[i])
        if row[0].startswith("第") and "試合" in row[0]:
            cur = {"date": _iso(row[1]), "teams": None, "rounds": []}
            games.append(cur)
        label = row[2]
        if "回戦" in label and cur is not None and cur["date"]:
            score_row = _pad(rows[i + 1]) if i + 1 < len(rows) else _pad([])
            scores, teams4 = [], []
            for c in (3, 5, 7, 9):
                name, team = row[c], row[c + 1]
                scores.append((name, _parse_point(score_row[c]), team))
                teams4.append(team)
            if cur["teams"] is None:
                cur["teams"] = teams4
            cur["rounds"].append({"round": label, "scores": scores})
            i += 2
            continue
        i += 1

    out = []
    for g in games:
        if not g["date"] or not g["rounds"]:
            continue
        m = int(g["date"][5:7])
        if not (m >= 9 or m <= regular_end_month):
            continue  # レギュラーシーズン外は除外
        out.append(g)
    return sorted(out, key=lambda x: x["date"])


def to_games(raw: list[dict]) -> list[Game]:
    out = []
    for g in raw:
        wd = _WD[date.fromisoformat(g["date"]).weekday()]
        rounds = [
            {"round": r["round"], "scores": [[n, p] for (n, p, _t) in r["scores"]]}
            for r in g["rounds"]
        ]
        out.append(Game(date=g["date"], weekday=wd, teams=g["teams"],
                        finished=True, key="", results=rounds))
    return out


def build_players(raw: list[dict], cfg) -> list[PlayerStanding]:
    short_by_team = {a.team: a.short for a in cfg.assignments}
    owner_by_team = cfg.owner_by_team
    pts: dict[str, float] = {}
    team_of: dict[str, str] = {}
    for g in raw:
        for rnd in g["rounds"]:
            for (name, pt, team) in rnd["scores"]:
                if not name:
                    continue
                pts[name] = pts.get(name, 0.0) + pt
                team_of[name] = team
    players = [
        PlayerStanding(
            player=name, team=team_of[name],
            short=short_by_team.get(team_of[name], ""),
            owner=owner_by_team.get(team_of[name], ""),
            point=round(pts[name], 1),
        )
        for name in pts
    ]
    players.sort(key=lambda p: p.point, reverse=True)
    return players


def main() -> None:
    cfg = load_teams_config()
    rows = _read_rows()
    raw = parse_raw(rows, cfg.regular_season_end_month)
    games = to_games(raw)
    save_schedule(SEASON, games)
    players = build_players(raw, cfg)
    save_player_ranking(SEASON, players)
    print(f"✅ {SEASON} 日程・結果を取り込み: {len(games)}試合 / 選手{len(players)}名")
    if games:
        print(f"   期間: {games[0].date} 〜 {games[-1].date}")
    if players:
        print(f"   選手1位: {players[0].player} {players[0].point:+.1f}")


if __name__ == "__main__":
    main()
