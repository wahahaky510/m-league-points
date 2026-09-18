"""m-league.jp/stats のスクレイピング。

去年の M-league_stats.py の scrape_all_teams() を切り出し、
DataFrame ではなく素直なデータ構造で返すよう整理した。
Sheets の書き込みロジックとは分離してある。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from playwright.sync_api import sync_playwright

from .config import STATS_URL


@dataclass
class TeamStats:
    """1チーム分の成績。"""

    name: str
    players: list[str]                     # 選手名の並び
    # 指標ラベル -> {選手名: 値(数値 or 文字列)}
    rows: dict[str, dict[str, object]] = field(default_factory=dict)

    def numeric_row(self, label: str) -> dict[str, float]:
        """指定指標を数値だけの辞書で返す（数値化できないものは除外）。"""
        out: dict[str, float] = {}
        for player, val in self.rows.get(label, {}).items():
            try:
                out[player] = float(str(val).replace(",", ""))
            except (TypeError, ValueError):
                continue
        return out


def _to_number(text: str) -> object:
    """数値に見えるものは float、そうでなければ元の文字列を返す。"""
    t = text.strip().replace(",", "")
    try:
        return float(t)
    except ValueError:
        return text.strip()


def scrape_all_teams() -> list[TeamStats]:
    """全チームの成績を取得して TeamStats のリストで返す。"""
    teams: list[TeamStats] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(STATS_URL, timeout=60000)
        page.wait_for_selector(".p-stats__table")

        team_name_elems = page.query_selector_all("h2.p-stats__teamName")
        team_tables = page.query_selector_all(".p-stats__tableInner")

        for idx, team_table in enumerate(team_tables):
            team_name = team_name_elems[idx].inner_text().strip()
            table = team_table.query_selector("table")
            rows = table.query_selector_all("tr")

            # 1行目 = ヘッダ（先頭は空欄、以降が選手名）
            players = [
                th.inner_text().strip()
                for th in rows[0].query_selector_all("th")[1:]
            ]

            stats = TeamStats(name=team_name, players=players)
            for row in rows[1:]:
                label = row.query_selector("th").inner_text().strip()
                tds = row.query_selector_all("td")
                values = [_to_number(td.inner_text()) for td in tds]
                stats.rows[label] = {
                    players[i]: values[i]
                    for i in range(min(len(players), len(values)))
                }
            teams.append(stats)

        browser.close()

    return teams


if __name__ == "__main__":
    result = scrape_all_teams()
    print(f"取得チーム数: {len(result)}")
    for t in result:
        print(f"- {t.name}: 選手{len(t.players)}名, 指標{len(t.rows)}項目")
    if result:
        print("指標ラベル一覧:", list(result[0].rows.keys()))
