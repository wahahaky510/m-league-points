"""m-league.jp の試合日程・結果の取得。

2026-11 のサイト刷新以降、日程ページは公式の JSON（/api/mleague/data?kind=games）
から描画されるため、それを直接読む（以前の HTML を月タブ巡回で読む方式は廃止）。
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from playwright.sync_api import sync_playwright

from .config import ROOT

GAMES_URL = "https://m-league.jp/games"


@dataclass
class Game:
    date: str          # ISO (YYYY-MM-DD)
    weekday: str       # 月/火/...
    teams: list[str]   # 対戦4チーム
    finished: bool
    key: str = ""      # サイトの試合キー "YYYYMMDD-通し番号"（消化済みのみ付く）
    # 消化済み試合の結果。rounds = [{"round":"第1回戦","scores":[[選手名, 得点], ...]}]
    results: list | None = None


def _season_start_year(season: str) -> int:
    """"2025-26" -> 2025。"""
    return int(season.split("-")[0])


def _iso_date(month: int, day: int, start_year: int) -> str:
    # 9〜12月は開始年、1〜8月は翌年
    year = start_year if month >= 9 else start_year + 1
    return date(year, month, day).isoformat()


GAMES_API = "https://m-league.jp/api/mleague/data?kind=games"
_WD = "月火水木金土日"


def _jst_date(iso_utc: str) -> date:
    """API の日時（UTC, 例 "2026-11-01T15:00:00.000Z"）を日本時間の日付にする。"""
    dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
    return (dt + timedelta(hours=9)).date()


def _fetch_games_json() -> dict:
    """公式サイトの日程 JSON を取得する。

    2026-11 のサイト刷新で、日程ページは /api/mleague/data?kind=games の JSON から
    描画されるようになった。サイトと同じ条件で取るため、ページを開いてから
    同一オリジンで fetch する。
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(GAMES_URL, timeout=60000)
        data = page.evaluate(
            """async (url) => {
              const r = await fetch(url, { cache: 'no-store' });
              if (!r.ok) throw new Error('HTTP ' + r.status);
              return await r.json();
            }""",
            GAMES_API,
        )
        browser.close()
    return data


def scrape_schedule(season: str, end_month: int = 3) -> list[Game]:
    """レギュラーシーズンの試合日程・結果を取得する。

    API は半荘(回戦)単位で、1件 = {date, no(回戦), desk(卓 0/1), complete, players[...]}。
    これを「日付＋卓」でまとめて 1試合（第1回戦・第2回戦）にする。
    end_month: レギュラーシーズン最終月（既定3=3月末まで）。4・5月は除外。
    """
    data = _fetch_games_json()
    phase = (data.get("season") or {}).get("phase")
    year = (data.get("season") or {}).get("year")
    if phase and phase != "regular":
        raise RuntimeError(f"レギュラーシーズン以外のデータです（phase={phase}）")
    if year and int(year) != _season_start_year(season):
        raise RuntimeError(f"シーズン不一致（API={year}, 設定={season}）")

    def in_regular(month: int) -> bool:
        return month >= 9 or month <= end_month

    groups: dict[tuple, list[dict]] = {}
    for h in data.get("games") or []:
        d = _jst_date(h["date"])
        if not in_regular(d.month):
            continue
        groups.setdefault((d, h.get("desk", 0)), []).append(h)

    games: list[Game] = []
    for (d, _desk), hs in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        hs.sort(key=lambda h: h.get("no") or 0)
        teams = [pl["team"] for pl in hs[0]["players"]]
        results = []
        for h in hs:
            if not h.get("complete"):
                continue
            ranked = sorted(h["players"], key=lambda pl: (pl.get("rank") or 9))
            results.append({
                "round": f"第{h.get('no')}回戦",
                "scores": [[(pl.get("name") or "").replace(" ", ""), float(pl.get("point") or 0)]
                           for pl in ranked],
            })
        finished = bool(hs) and all(h.get("complete") for h in hs)
        games.append(Game(
            date=d.isoformat(), weekday=_WD[d.weekday()], teams=teams,
            finished=finished, key=re.sub(r"_\d+[A-Z]?$", "", hs[0]["id"]) + "-" + str(_desk),
            results=results or None,
        ))
    if not games:
        raise RuntimeError("日程データが空でした")
    return games


def _parse_point(text: str) -> float:
    """"58pt" -> 58.0 / "▲19.5pt" -> -19.5。"""
    t = text.replace("pt", "").replace(",", "").strip()
    neg = t.startswith("▲") or t.startswith("△") or t.startswith("-")
    t = t.lstrip("▲△-").strip()
    try:
        v = float(t)
    except ValueError:
        return 0.0
    return -v if neg else v


def _game_id(g: Game) -> tuple:
    """試合の同一判定キー。チームの並び順・空白の違いに左右されないようにする。

    （2026-11 の公式サイト刷新でロゴの並び順や「KONAMI 麻雀格闘倶楽部」の
    空白が変わり、並び順依存の照合で保存済み結果が全部外れたため）
    """
    return (g.date, frozenset(t.replace(" ", "").replace("　", "") for t in g.teams))


def merge_results(new_games: list[Game], old_games: list[Game]) -> list[Game]:
    """既に保存済みの結果を引き継ぐ（蓄積）。

    一度取得した試合結果は最終値なので、サイトが古いモーダルを
    落としても失わないよう、新規スクレイプに保存済みの結果を補完する。
    消化済みフラグ・キーも保存済み側を引き継ぐ。
    """
    old_by = {_game_id(g): g for g in old_games}
    for g in new_games:
        o = old_by.get(_game_id(g))
        if not o:
            continue
        if not g.results and o.results:
            g.results = o.results
        g.finished = g.finished or o.finished or bool(g.results)
        if not g.key:
            g.key = o.key
    return new_games


# --- 永続化 ---
def save_schedule(season: str, games: list[Game]) -> Path:
    out_dir = ROOT / "data" / "seasons" / season
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "schedule.json"
    out.write_text(
        json.dumps([asdict(g) for g in games], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out


def load_schedule(season: str) -> list[Game]:
    f = ROOT / "data" / "seasons" / season / "schedule.json"
    if not f.exists():
        return []
    return [Game(**g) for g in json.loads(f.read_text(encoding="utf-8"))]


def seasons_with_schedule() -> list[str]:
    """schedule.json を持つシーズンを新しい順で返す。"""
    base = ROOT / "data" / "seasons"
    if not base.exists():
        return []
    seasons = [d.name for d in base.iterdir()
               if (d / "schedule.json").exists()]
    return sorted(seasons, reverse=True)


if __name__ == "__main__":
    from .config import load_teams_config

    cfg = load_teams_config()
    gs = scrape_schedule(cfg.season)
    print(f"取得試合数: {len(gs)}")
    for g in gs[:8]:
        mark = "✅" if g.finished else "　"
        print(f"{mark} {g.date}（{g.weekday}） {' / '.join(g.teams)}")
    print("...")
    print("最終試合:", gs[-1].date if gs else "なし")
