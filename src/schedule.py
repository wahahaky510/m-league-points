"""m-league.jp/games（試合日程）のスクレイピングとカレンダー生成。

日程ページは月タブ（9月〜翌5月）で切り替わり、各試合は
  .p-gamesSchedule2__list
    .p-gamesSchedule2__data   … "10/1（水）" のような日付
    .p-gamesSchedule2__logos img[alt] … 対戦4チーム名
    class に is-finish が付くと消化済み
という構造。全月タブを順にクリックして全試合を集める。

シーズンは 9〜12月＝開始年 / 1〜5月＝翌年 として日付を確定する。
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import date
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


def scrape_schedule(season: str, end_month: int = 3) -> list[Game]:
    """レギュラーシーズンの試合日程を取得する。

    end_month: レギュラーシーズン最終月（既定3=3月末まで）。
    4・5月のセミ/ファイナルは集計対象外なので除外する。
    """
    start_year = _season_start_year(season)
    games: dict[tuple, Game] = {}

    def in_regular(month: int) -> bool:
        return month >= 9 or month <= end_month

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(GAMES_URL, timeout=60000)
        page.wait_for_selector(".p-gamesSchedule2__list", timeout=30000)

        # 月タブは切替でセクションが再描画され、要素ハンドルが無効化される。
        # そのため「月ラベルの一覧」だけ先に取り、各月はその都度取り直してクリックする。
        tab_sel = ".p-gamesSchedule2__tab-item, .p-gamesSchedule2__tab-list li"
        month_labels: list[str] = []
        for t in page.query_selector_all(tab_sel):
            label = (t.inner_text() or "").strip()
            if re.fullmatch(r"\d+月", label) and label not in month_labels:
                month_labels.append(label)

        def click_month(label: str) -> bool:
            for t in page.query_selector_all(tab_sel):
                if (t.inner_text() or "").strip() == label:
                    t.click()
                    return True
            return False

        def collect_current() -> None:
            for it in page.query_selector_all(".p-gamesSchedule2__list"):
                data_el = it.query_selector(".p-gamesSchedule2__data")
                if not data_el:
                    continue
                raw = data_el.inner_text().strip()
                m = re.search(r"(\d+)\s*/\s*(\d+)", raw)
                if not m:
                    continue
                month, day = int(m.group(1)), int(m.group(2))
                if not in_regular(month):
                    continue  # 4・5月（セミ/ファイナル）は除外
                wd = re.search(r"（(.)）", raw)
                weekday = wd.group(1) if wd else ""
                teams = [
                    img.get_attribute("alt").strip()
                    for img in it.query_selector_all(".p-gamesSchedule2__logos img")
                    if img.get_attribute("alt")
                ]
                finished = "is-finish" in (it.get_attribute("class") or "")
                dt = it.get_attribute("data-target") or ""
                key = dt.replace("key", "") if dt.startswith("key") else ""
                iso = _iso_date(month, day, start_year)
                games[(iso, tuple(teams))] = Game(
                    date=iso, weekday=weekday, teams=teams, finished=finished, key=key
                )

        collect_current()  # 初期表示（当月）
        for label in month_labels:
            try:
                if click_month(label):
                    # タブ切替はAJAXで中身が入れ替わるため十分に待つ
                    page.wait_for_timeout(2500)
                    collect_current()
            except Exception:
                continue

        # 消化済み試合の結果モーダル（js-modal-key<日付>-<番号>）をまとめて抽出
        raw_results = page.evaluate(
            """() => {
              const out = {};
              document.querySelectorAll('.c-modal2').forEach(m => {
                if (!m.id.startsWith('js-modal-key') || m.id.includes('年')) return;
                const key = m.id.replace('js-modal-key', '');
                const rounds = [];
                m.querySelectorAll('.p-gamesResult__column').forEach(col => {
                  const rn = (col.querySelector('.p-gamesResult__number') || {}).innerText || '';
                  const scores = [];
                  col.querySelectorAll('.p-gamesResult__rank-item').forEach(it => {
                    const nm = (it.querySelector('.p-gamesResult__name') || {}).innerText || '';
                    const pt = (it.querySelector('.p-gamesResult__point') || {}).innerText || '';
                    if (nm.trim()) scores.push([nm.trim(), pt.trim()]);
                  });
                  if (scores.length) rounds.push({ round: rn.trim(), scores });
                });
                if (rounds.length) out[key] = rounds;
              });
              return out;
            }"""
        )

        browser.close()

    # 結果を各試合に紐付け（得点は ▲=マイナスで数値化）
    for g in games.values():
        rounds = raw_results.get(g.key)
        if rounds:
            g.results = [
                {"round": r["round"],
                 "scores": [[nm, _parse_point(pt)] for nm, pt in r["scores"]]}
                for r in rounds
            ]

    return sorted(games.values(), key=lambda g: g.date)


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


def merge_results(new_games: list[Game], old_games: list[Game]) -> list[Game]:
    """既に保存済みの結果を引き継ぐ（蓄積）。

    一度取得した試合結果は最終値なので、サイトが古いモーダルを
    落としても失わないよう、新規スクレイプに保存済みの結果を補完する。
    """
    old_by = {(g.date, tuple(g.teams)): g for g in old_games}
    for g in new_games:
        o = old_by.get((g.date, tuple(g.teams)))
        if not o:
            continue
        if not g.results and o.results:
            g.results = o.results
            g.finished = g.finished or o.finished
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
