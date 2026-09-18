"""集計ロジック：チーム順位・個人（担当）順位を計算する。

去年はシートの行番号決め打ち＋XLOOKUP式で組んでいたが、
今年は teams.yaml の担当マッピングを使ってPython側で完結させる。
結果は JSON スナップショットとして data/ に保存し、
Sheets / LINE / ダッシュボードの共通ソースにする。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

from .config import ROOT, TeamsConfig
from .scraper import TeamStats


@dataclass
class TeamStanding:
    team: str
    short: str
    owner: str
    point: float
    color: str = "#888888"
    top: str = ""
    main: str = ""
    games: int = 0


@dataclass
class MemberStanding:
    name: str
    point: float
    teams: list[str] = field(default_factory=list)


@dataclass
class PlayerStanding:
    """Mリーグ選手（プロ）個人ランキングの1件。"""

    player: str
    team: str
    short: str
    owner: str      # そのチームの身内担当（いなければ空）
    point: float


@dataclass
class Snapshot:
    """ある時点の集計結果。JSONに落とせる形。"""

    date: str
    season: str
    teams: list[TeamStanding]     # ポイント降順
    members: list[MemberStanding]  # ポイント降順

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "season": self.season,
            "teams": [asdict(t) for t in self.teams],
            "members": [asdict(m) for m in self.members],
        }


def build_snapshot(
    stats: list[TeamStats],
    teams_cfg: TeamsConfig,
    on: date | None = None,
) -> Snapshot:
    """スクレイピング結果と担当設定から Snapshot を作る。"""
    on = on or date.today()
    owner_by_team = teams_cfg.owner_by_team
    by_team = {a.team: a for a in teams_cfg.assignments}
    label = teams_cfg.total_point_label

    team_standings: list[TeamStanding] = []
    for st in stats:
        point = sum(st.numeric_row(label).values())
        games = int(round(sum(st.numeric_row("試合数").values())))
        a = by_team.get(st.name)
        team_standings.append(
            TeamStanding(
                team=st.name,
                short=a.short if a else "",
                owner=owner_by_team.get(st.name, ""),
                point=round(point, 1),
                color=a.color if a else "#888888",
                top=a.top if a else "",
                main=(a.main if a and a.main else (a.short if a else st.name)),
                games=games,
            )
        )
    team_standings.sort(key=lambda t: t.point, reverse=True)

    # 個人（担当）集計：担当チームのポイントを合算
    member_points: dict[str, float] = {m: 0.0 for m in teams_cfg.members}
    member_teams: dict[str, list[str]] = {m: [] for m in teams_cfg.members}
    for ts in team_standings:
        if ts.owner and ts.owner in member_points:
            member_points[ts.owner] += ts.point
            member_teams[ts.owner].append(ts.team)

    member_standings = [
        MemberStanding(name=m, point=round(member_points[m], 1), teams=member_teams[m])
        for m in teams_cfg.members
    ]
    member_standings.sort(key=lambda m: m.point, reverse=True)

    return Snapshot(
        date=on.isoformat(),
        season=teams_cfg.season,
        teams=team_standings,
        members=member_standings,
    )


def build_player_ranking(
    stats: list[TeamStats], teams_cfg: TeamsConfig
) -> list[PlayerStanding]:
    """Mリーグ全選手をポイント降順で並べた個人ランキングを作る。"""
    owner_by_team = teams_cfg.owner_by_team
    short_by_team = {a.team: a.short for a in teams_cfg.assignments}
    label = teams_cfg.total_point_label

    players: list[PlayerStanding] = []
    for st in stats:
        for player, pt in st.numeric_row(label).items():
            players.append(
                PlayerStanding(
                    player=player,
                    team=st.name,
                    short=short_by_team.get(st.name, ""),
                    owner=owner_by_team.get(st.name, ""),
                    point=round(pt, 1),
                )
            )
    players.sort(key=lambda p: p.point, reverse=True)
    return players


def save_player_ranking(season: str, players: list[PlayerStanding]) -> Path:
    sdir = _season_dir(season)
    sdir.mkdir(parents=True, exist_ok=True)
    out = sdir / "players.json"
    out.write_text(
        json.dumps([asdict(p) for p in players], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out


def load_player_ranking(season: str) -> list[PlayerStanding]:
    f = _season_dir(season) / "players.json"
    if not f.exists():
        return []
    return [PlayerStanding(**p) for p in json.loads(f.read_text(encoding="utf-8"))]


# --- スナップショットの永続化（シーズン別） ---
# 得点はシーズンごとに独立。data/seasons/<season>/ 配下に貯める。
# data/latest.json は「現シーズンの最新」を指す（LINE・ダッシュボード用）。
DATA_DIR = ROOT / "data"
SEASONS_DIR = DATA_DIR / "seasons"


def _season_dir(season: str) -> Path:
    return SEASONS_DIR / season


def _snap_from_dict(d: dict) -> Snapshot:
    return Snapshot(
        date=d["date"],
        season=d["season"],
        teams=[TeamStanding(**t) for t in d["teams"]],
        members=[MemberStanding(**m) for m in d["members"]],
    )


def save_snapshot(snap: Snapshot, set_global_latest: bool = True) -> Path:
    """スナップショットを保存し、各種インデックスを更新する。

    set_global_latest: 現シーズンの実行では True（data/latest.json も更新）。
    過去シーズンをアーカイブ投入する際は False（現シーズンの最新を壊さない）。
    """
    sdir = _season_dir(snap.season)
    snap_dir = sdir / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)

    payload = json.dumps(snap.to_dict(), ensure_ascii=False, indent=2)

    dated = snap_dir / f"{snap.date}.json"
    dated.write_text(payload, encoding="utf-8")

    # シーズン内の latest / history
    (sdir / "latest.json").write_text(payload, encoding="utf-8")
    _rebuild_history(snap.season)

    # グローバルの「現シーズン最新」
    if set_global_latest:
        (DATA_DIR / "latest.json").write_text(payload, encoding="utf-8")
    return dated


def _rebuild_history(season: str) -> Path:
    """そのシーズンの snapshots/*.json をまとめた history.json を作る。"""
    snap_dir = _season_dir(season) / "snapshots"
    snaps = [
        json.loads(f.read_text(encoding="utf-8"))
        for f in sorted(snap_dir.glob("*.json"))
    ]
    history = _season_dir(season) / "history.json"
    history.write_text(
        json.dumps(snaps, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return history


def list_seasons() -> list[str]:
    """データのあるシーズンを新しい順で返す。"""
    if not SEASONS_DIR.exists():
        return []
    seasons = [d.name for d in SEASONS_DIR.iterdir() if d.is_dir()]
    return sorted(seasons, reverse=True)


def load_latest() -> Snapshot | None:
    """グローバルの現シーズン最新スナップショット。"""
    latest = DATA_DIR / "latest.json"
    if not latest.exists():
        return None
    return _snap_from_dict(json.loads(latest.read_text(encoding="utf-8")))


def load_season_latest(season: str) -> Snapshot | None:
    f = _season_dir(season) / "latest.json"
    if not f.exists():
        return None
    return _snap_from_dict(json.loads(f.read_text(encoding="utf-8")))


def load_season_history(season: str) -> list[dict]:
    f = _season_dir(season) / "history.json"
    if not f.exists():
        return []
    return json.loads(f.read_text(encoding="utf-8"))
