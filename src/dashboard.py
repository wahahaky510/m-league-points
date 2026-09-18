"""GitHub Pages 用ダッシュボードを生成する。

- docs/index.html          現シーズンの順位＋推移グラフ
- docs/season-<season>.html 各シーズンのアーカイブページ
- docs/archive.html         シーズン一覧

得点はシーズンごとに独立（data/seasons/<season>/ 配下）なので、
index.html は常に現シーズンのみを表示する。
"""
from __future__ import annotations

import json
from pathlib import Path

import calendar as _cal

from .config import ROOT, TeamsConfig, load_teams_config
from .schedule import load_schedule
from .standings import (
    Snapshot,
    list_seasons,
    load_latest,
    load_player_ranking,
    load_season_history,
    load_season_latest,
)

DOCS_DIR = ROOT / "docs"

_PALETTE = [
    "#4E79A7", "#F28E2B", "#59A14F", "#E15759", "#B07AA1", "#76B7B2",
    "#EDC948", "#FF9DA7", "#9C755F", "#BAB0AC",
]

# 身内メンバーの色（カレンダーで担当チームを色分け）
_MEMBER_COLORS = [
    "#4E79A7", "#F28E2B", "#59A14F", "#E15759", "#B07AA1", "#76B7B2", "#EDC948",
]


def _member_series(history: list[dict]) -> dict:
    """推移グラフ用データ：{labels:[日付], datasets:[{label,data,color}]}。"""
    labels = [h["date"] for h in history]
    names: list[str] = []
    for h in history:
        for m in h["members"]:
            if m["name"] not in names:
                names.append(m["name"])
    datasets = []
    for i, name in enumerate(names):
        data = [
            next((m["point"] for m in h["members"] if m["name"] == name), None)
            for h in history
        ]
        datasets.append(
            {"label": name, "data": data, "color": _PALETTE[i % len(_PALETTE)]}
        )
    return {"labels": labels, "datasets": datasets}


def _rows_html(items: list[dict], name_key: str, sub_fn=None) -> str:
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    out = []
    for i, it in enumerate(items, 1):
        medal = medals.get(i, str(i))
        point = it["point"]
        cls = "pos" if point >= 0 else "neg"
        sub = f'<span class="sub">{sub_fn(it)}</span>' if sub_fn else ""
        out.append(
            f'<tr><td class="rank">{medal}</td>'
            f'<td class="name">{it[name_key]}{sub}</td>'
            f'<td class="pt {cls}">{point:+.1f}</td></tr>'
        )
    return "\n".join(out)


def _rank_label(i: int, n: int) -> str:
    """順位表示。下位2名は「雑魚」「クソ雑魚」、上位3名はメダル、他は数字。"""
    if n >= 2 and i == n:
        return "クソ雑魚"
    if n >= 3 and i == n - 1:
        return "雑魚"
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, str(i))


def _member_rows_html(members: list[dict]) -> str:
    n = len(members)
    out = []
    for i, m in enumerate(members, 1):
        point = m["point"]
        cls = "pos" if point >= 0 else "neg"
        label = _rank_label(i, n)
        low = " low" if label in ("雑魚", "クソ雑魚") else ""
        out.append(
            f'<tr><td class="rank{low}">{label}</td>'
            f'<td class="name">{m["name"]}</td>'
            f'<td class="pt {cls}">{point:+.1f}</td></tr>'
        )
    return "\n".join(out)


def _fill(template: str, mapping: dict[str, str]) -> str:
    """__KEY__ 形式のプレースホルダを置換する（.format のbrace衝突を避ける）。"""
    out = template
    for k, v in mapping.items():
        out = out.replace(f"__{k}__", v)
    return out


def _team_broadcast_html(teams: list, games_total: int, prev_ranks: dict) -> str:
    """Mリーグ放送風のチームランキング（色バー・順位・ポイント・差・試合数）。"""
    rows = []
    for i, t in enumerate(teams, 1):
        prev = prev_ranks.get(t.team)
        arrow = ""
        if prev is not None:
            if i < prev:
                arrow = '<span class="arw up">▲</span>'
            elif i > prev:
                arrow = '<span class="arw dn">▼</span>'
        diff = "-" if i == 1 else f"{teams[i - 2].point - t.point:.1f}"
        top = f'<div class="ttop">{t.top}</div>' if t.top else ""
        main = t.main or t.short or t.team
        rows.append(
            f'<div class="trow">'
            f'<div class="trank" style="background:{t.color}">{i}</div>'
            f'<div class="tname" style="background:linear-gradient(90deg,{t.color}55,{t.color}0d)">'
            f'{top}<div class="tmain">{main}</div></div>'
            f'<div class="tpt">{t.point:+.1f}{arrow}</div>'
            f'<div class="tdiff">{diff}</div>'
            f'<div class="tgames">{t.games}<span>/{games_total}</span></div>'
            f'</div>'
        )
    header = (
        '<div class="trow thead">'
        '<div class="trank"></div>'
        '<div class="tname">チームランキング</div>'
        '<div class="tpt">トータル</div>'
        '<div class="tdiff">ポイント差</div>'
        '<div class="tgames">試合数</div>'
        '</div>'
    )
    return header + "\n".join(rows)


def _page(snap: Snapshot, history: list[dict], nav_html: str, subtitle: str,
          games_total: int = 120) -> str:
    series = _member_series(history)
    member_rows = _member_rows_html([m.__dict__ for m in snap.members])

    # ひとつ前のスナップショットからチーム順位変動（▲▼）を出す
    prev_ranks: dict[str, int] = {}
    if len(history) >= 2:
        for i, t in enumerate(history[-2]["teams"], 1):
            prev_ranks[t["team"]] = i
    team_bc = _team_broadcast_html(snap.teams, games_total, prev_ranks)

    return _fill(_TEMPLATE, {
        "SEASON": snap.season,
        "SUBTITLE": subtitle,
        "NAV": nav_html,
        "MEMBER_ROWS": member_rows,
        "TEAM_BROADCAST": team_bc,
        "CHART_DATA": json.dumps(series, ensure_ascii=False),
    })


def render(snap: Snapshot | None = None) -> Path:
    """全ページを生成する。snap を渡さない場合は現シーズン最新を使う。"""
    snap = snap or load_latest()
    if snap is None:
        raise RuntimeError("latest.json がありません。先に集計を実行してください。")

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    seasons = list_seasons()
    current = snap.season
    games_total = load_teams_config().games_total

    # --- index.html（現シーズン） ---
    nav = _nav_html(current=current, seasons=seasons, active="current")
    history = load_season_history(current)
    (DOCS_DIR / "index.html").write_text(
        _page(snap, history, nav, f"{snap.date} 時点（現シーズン）", games_total),
        encoding="utf-8",
    )

    # --- 各シーズンのアーカイブページ ---
    for s in seasons:
        s_snap = load_season_latest(s)
        if s_snap is None:
            continue
        s_hist = load_season_history(s)
        s_nav = _nav_html(current=current, seasons=seasons, active=s)
        (DOCS_DIR / f"season-{s}.html").write_text(
            _page(s_snap, s_hist, s_nav, f"最終更新 {s_snap.date}（アーカイブ）", games_total),
            encoding="utf-8",
        )

    # --- archive.html（シーズン一覧） ---
    (DOCS_DIR / "archive.html").write_text(
        _archive_page(seasons, current), encoding="utf-8"
    )

    # --- 日程カレンダー（日程データを持つ各シーズン） ---
    try:
        from .schedule import seasons_with_schedule
        sched_seasons = seasons_with_schedule() or [current]
        # 現シーズンに日程が無くても calendar.html は生成する
        for s in dict.fromkeys([current, *sched_seasons]):
            render_calendar(s, current=current, sched_seasons=sched_seasons)
    except Exception as e:
        print(f"   カレンダー生成スキップ（{e}）")

    # --- players.html（Mリーグ選手個人ランキング） ---
    try:
        render_players(current)
    except Exception as e:
        print(f"   選手ランキング生成スキップ（{e}）")

    print(f"✅ ダッシュボード生成: index + players + calendar + archive + {len(seasons)}シーズン")
    return DOCS_DIR / "index.html"


def _nav_html(current: str, seasons: list[str], active: str) -> str:
    """ページ上部のナビ。active は 'current' / 'calendar' / 'players' /
    'archive' / season名 のいずれか（該当タブだけ青くする）。"""
    def a(label: str, href: str, key: str) -> str:
        cls = "active" if active == key else ""
        return f'<a class="{cls}" href="{href}">{label}</a>'

    # 過去シーズンはアーカイブからのみ辿る（タブには出さない）
    links = [
        a("今シーズン", "index.html", "current"),
        a("🎴 選手", "players.html", "players"),
        a("📅 日程", "calendar.html", "calendar"),
        a("📚 アーカイブ", "archive.html", "archive"),
    ]
    return '<nav class="seasons">' + "".join(links) + "</nav>"


# ============================== 日程カレンダー ==============================

def _member_color_map(cfg: TeamsConfig) -> dict[str, str]:
    return {m: _MEMBER_COLORS[i % len(_MEMBER_COLORS)]
            for i, m in enumerate(cfg.members)}


def _calendar_filename(season: str, current: str) -> str:
    return "calendar.html" if season == current else f"calendar-{season}.html"


def _season_picker(view_season: str, current: str, sched_seasons: list[str]) -> str:
    """日程ページのシーズン切替（表示中のシーズンをハイライト）。"""
    if len(sched_seasons) <= 1:
        return ""
    pills = []
    for s in sched_seasons:
        cls = "active" if s == view_season else ""
        href = _calendar_filename(s, current)
        label = s + ("（今）" if s == current else "")
        pills.append(f'<a class="{cls}" href="{href}">{label}</a>')
    return ('<div class="season-picker"><span>シーズン:</span>'
            + "".join(pills) + "</div>")


def render_calendar(season: str, cfg: TeamsConfig | None = None,
                    current: str | None = None,
                    sched_seasons: list[str] | None = None) -> Path:
    """指定シーズンの日程カレンダーを生成する。

    current（現シーズン）は calendar.html、それ以外は calendar-<season>.html。
    """
    cfg = cfg or load_teams_config()
    current = current or cfg.season
    sched_seasons = sched_seasons if sched_seasons is not None else [season]
    games = load_schedule(season)
    seasons = list_seasons()
    nav = _nav_html(current=current, seasons=seasons, active="calendar")
    picker = _season_picker(season, current, sched_seasons)

    # 日程ページと成績ページでチーム名の空白有無が異なる場合があるため、
    # 空白を除いたキーで突き合わせる（例: "KONAMI 麻雀格闘倶楽部" vs "KONAMI麻雀格闘倶楽部"）
    def _norm(s: str) -> str:
        return "".join(s.split())

    owner_by_team = {_norm(k): v for k, v in cfg.owner_by_team.items()}
    short_by_team = {_norm(a.team): a.short for a in cfg.assignments}
    color_by_team = {_norm(a.team): a.color for a in cfg.assignments}
    color_by_member = _member_color_map(cfg)

    # 日付 -> その日の試合リスト
    by_date: dict[str, list] = {}
    for g in games:
        by_date.setdefault(g.date, []).append(g)

    # 対象月（YYYY-MM）を昇順で
    months = sorted({g.date[:7] for g in games})

    def tile(team: str) -> str:
        """チームカラーのタイル1枚。右に担当メンバー名を添える。"""
        key = _norm(team)
        color = color_by_team.get(key, "#555")
        owner = owner_by_team.get(key, "")
        label = short_by_team.get(key) or team
        own = f'<span class="to">{owner}</span>' if owner else ""
        return f'<span class="tile" style="background:{color}">{label}{own}</span>'

    def game_block(g, idx: int, n: int) -> str:
        fin = " finished" if g.finished else ""
        mark = "✓" if g.finished else ""
        num = f'<span class="gnum">第{idx}試合</span>' if n > 1 else ""
        tiles = "".join(tile(t) for t in g.teams)
        return (f'<div class="game{fin}">'
                f'<div class="ghd">{num}<span class="gmk">{mark}</span></div>'
                f'<div class="tiles">{tiles}</div></div>')

    months_html = []
    for ym in months:
        y, m = int(ym[:4]), int(ym[5:7])
        cells = []
        # 曜日ヘッダ（日〜土）
        for w in ["日", "月", "火", "水", "木", "金", "土"]:
            cells.append(f'<div class="cal-h">{w}</div>')
        # 月初の空白（日曜始まり: Sun=6→0 に変換）
        first_wd = (_cal.weekday(y, m, 1) + 1) % 7  # Mon=0..Sun=6 -> Sun=0
        for _ in range(first_wd):
            cells.append('<div class="cal-c empty"></div>')
        ndays = _cal.monthrange(y, m)[1]
        for d in range(1, ndays + 1):
            iso = f"{y:04d}-{m:02d}-{d:02d}"
            day_games = by_date.get(iso, [])
            inner = f'<div class="cal-d">{d}</div>'
            n = len(day_games)
            for idx, g in enumerate(day_games, 1):
                inner += game_block(g, idx, n)
            if day_games:
                multi = " multi" if n > 1 else ""
                cells.append(
                    f'<div class="cal-c has-games{multi}" data-date="{iso}" '
                    f'tabindex="0" role="button">{inner}</div>'
                )
            else:
                cells.append(f'<div class="cal-c">{inner}</div>')
        months_html.append(
            f'<div class="cal-month"><h3>{y}年{m}月</h3>'
            f'<div class="cal-grid">{"".join(cells)}</div></div>'
        )

    # 凡例：各チームをチームカラーのタイルで示す（右の小文字＝担当メンバー）
    legend_items = []
    for a in cfg.assignments:
        own = f'<span class="to">{a.owner}</span>' if a.owner else ""
        legend_items.append(
            f'<span class="tile" style="background:{a.color}">'
            f'{a.short or a.team}{own}</span>'
        )
    legend = ('<span class="lgnote">タイル右の小文字＝担当メンバー</span>'
              + "".join(legend_items))

    # 日付タップ時の拡大表示（モーダル）用データ
    teams_map = {
        _norm(a.team): {"name": a.team, "short": a.short,
                        "owner": a.owner, "color": a.color}
        for a in cfg.assignments
    }
    days_map = {
        iso: [
            {"teams": [_norm(t) for t in g.teams],
             "raw": list(g.teams), "finished": g.finished,
             "results": g.results}
            for g in gs
        ]
        for iso, gs in by_date.items()
    }
    # 選手名（空白除去）→ 所属チームの短縮名・色（結果表示の色分け用）
    players_map = {
        _norm(p.player): {
            "short": p.short or p.team,
            "color": color_by_team.get(_norm(p.team), "#666"),
        }
        for p in load_player_ranking(season)
    }
    cal_data = json.dumps(
        {"teams": teams_map, "days": days_map, "players": players_map},
        ensure_ascii=False,
    )

    html = _fill(_CAL_TEMPLATE, {
        "SEASON": season,
        "NAV": nav,
        "PICKER": picker,
        "LEGEND": legend,
        "MONTHS": "\n".join(months_html) or "<p>日程データがありません。</p>",
        "CAL_DATA": cal_data,
    })
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    out = DOCS_DIR / _calendar_filename(season, current)
    out.write_text(html, encoding="utf-8")
    return out


# ========================= Mリーグ選手個人ランキング =========================

def render_players(season: str, cfg: TeamsConfig | None = None) -> Path:
    """docs/players.html を生成する（Mリーグ全選手のポイント順）。"""
    cfg = cfg or load_teams_config()
    players = load_player_ranking(season)
    seasons = list_seasons()
    nav = _nav_html(current=season, seasons=seasons, active="players")
    color_by_member = _member_color_map(cfg)

    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    rows = []
    for i, p in enumerate(players, 1):
        medal = medals.get(i, str(i))
        cls = "pos" if p.point >= 0 else "neg"
        team_label = p.short or p.team
        if p.owner:
            color = color_by_member.get(p.owner, "#888")
            team_html = (f'<span class="pteam">{team_label}</span>'
                         f'<span class="pown" style="color:{color}">◆{p.owner}</span>')
        else:
            team_html = f'<span class="pteam">{team_label}</span>'
        rows.append(
            f'<tr><td class="rank">{medal}</td>'
            f'<td class="name">{p.player}<br>{team_html}</td>'
            f'<td class="pt {cls}">{p.point:+.1f}</td></tr>'
        )

    html = _fill(_PLAYERS_TEMPLATE, {
        "SEASON": season,
        "NAV": nav,
        "ROWS": "\n".join(rows) or "<tr><td>データがありません。</td></tr>",
    })
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    out = DOCS_DIR / "players.html"
    out.write_text(html, encoding="utf-8")
    return out


def _archive_page(seasons: list[str], current: str) -> str:
    cards = []
    for s in seasons:
        snap = load_season_latest(s)
        if snap is None:
            continue
        top = snap.members[0] if snap.members else None
        badge = "（今シーズン）" if s == current else ""
        href = "index.html" if s == current else f"season-{s}.html"
        top_html = (
            f'<div class="atop">👑 {top.name} <span class="pt pos">'
            f'{top.point:+.1f}</span></div>'
            if top
            else ""
        )
        cards.append(
            f'<a class="acard" href="{href}">'
            f'<div class="atitle">{s}{badge}</div>'
            f'<div class="ameta">最終更新 {snap.date}</div>'
            f'{top_html}</a>'
        )
    return _fill(_ARCHIVE_TEMPLATE, {
        "CARDS": "\n".join(cards) or "<p>まだデータがありません。</p>",
    })


_STYLE = """
  :root {
    --bg: #14141f; --card: #1e1e2e; --line: #2c2c3c;
    --fg: #e8e8f0; --muted: #9a9ab0; --accent: #7c5cff;
    --pos: #4caf7d; --neg: #ef5f6b;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--fg);
    font-family: -apple-system, "Hiragino Kaku Gothic ProN", "Meiryo", sans-serif;
    padding: 16px;
  }
  .wrap { max-width: 900px; margin: 0 auto; }
  h1 { font-size: 1.4rem; margin: 8px 0 2px; }
  .meta { color: var(--muted); font-size: .8rem; margin-bottom: 12px; }
  nav.seasons { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }
  nav.seasons a {
    font-size: .8rem; text-decoration: none; color: var(--muted);
    border: 1px solid var(--line); padding: 4px 10px; border-radius: 999px;
  }
  nav.seasons a.active { background: var(--accent); color: #fff; border-color: var(--accent); }
  .grid { display: grid; grid-template-columns: 1fr; gap: 16px; }
  @media (min-width: 700px) { .grid { grid-template-columns: 1fr 1fr; } }
  .card {
    background: var(--card); border: 1px solid var(--line);
    border-radius: 12px; padding: 14px 16px;
  }
  .card h2 { font-size: 1rem; margin: 0 0 10px; }
  table { width: 100%; border-collapse: collapse; }
  td { padding: 8px 4px; border-bottom: 1px solid var(--line); font-size: .95rem; }
  tr:last-child td { border-bottom: none; }
  .rank { width: 36px; text-align: center; color: var(--muted); }
  .rank.low { width: auto; white-space: nowrap; color: var(--neg); font-weight: 700;
              font-size: .82rem; padding-right: 6px; }
  .name { font-weight: 600; }
  .sub { color: var(--muted); font-weight: 400; font-size: .78rem; margin-left: 4px; }
  .pt { text-align: right; font-variant-numeric: tabular-nums; font-weight: 700; width: 84px; }
  .pos { color: var(--pos); }
  .neg { color: var(--neg); }
  .chart-card { margin-top: 16px; }
  footer { color: var(--muted); font-size: .72rem; text-align: center; margin-top: 24px; }
  .acard {
    display: block; text-decoration: none; color: var(--fg);
    background: var(--card); border: 1px solid var(--line);
    border-radius: 12px; padding: 16px; margin-bottom: 12px;
  }
  .acard:hover { border-color: var(--accent); }
  .atitle { font-weight: 700; font-size: 1.1rem; }
  .ameta { color: var(--muted); font-size: .78rem; margin: 4px 0; }
  .atop { font-size: .95rem; }
  /* --- カレンダー --- */
  .season-picker { display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
                   margin: 4px 0 14px; }
  .season-picker > span { font-size: .78rem; color: var(--muted); }
  .season-picker a { font-size: .8rem; text-decoration: none; color: var(--muted);
                     border: 1px solid var(--line); padding: 4px 12px;
                     border-radius: 999px; }
  .season-picker a.active { background: var(--accent); color: #fff;
                            border-color: var(--accent); }
  .legend { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0 18px;
            align-items: center; }
  .legend .tile { font-size: .66rem; }
  .lgnote { font-size: .72rem; color: var(--muted); margin-right: 4px; }
  .lg { display: inline-flex; align-items: center; gap: 5px; }
  .dot { width: 11px; height: 11px; border-radius: 50%; display: inline-block; }
  .cal-month { margin-bottom: 26px; }
  .cal-month h3 { font-size: 1.05rem; margin: 0 0 8px; }
  .cal-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 4px; }
  .cal-h { text-align: center; font-size: .72rem; color: var(--muted);
           padding: 2px 0; }
  .cal-c { min-height: 62px; background: var(--card); border: 1px solid var(--line);
           border-radius: 6px; padding: 4px; }
  .cal-c.empty { background: transparent; border: none; }
  .cal-d { font-size: .72rem; color: var(--muted); margin-bottom: 3px; }
  /* 1試合ぶん = チームカラーの2x2タイル。試合ごとに枠で区切る */
  .game { margin-bottom: 5px; padding: 3px; border-radius: 6px;
          background: rgba(255,255,255,.035); }
  .game:last-child { margin-bottom: 0; }
  .game.finished { opacity: .4; }
  .ghd { display: flex; justify-content: space-between; align-items: center;
         height: 11px; margin-bottom: 2px; }
  .gnum { font-size: .54rem; color: var(--muted); font-weight: 700; }
  .gmk { color: var(--pos); font-size: .62rem; }
  .tiles { display: grid; grid-template-columns: 1fr 1fr; gap: 2px; }
  .tile { display: flex; justify-content: space-between; align-items: center;
          font-size: .6rem; font-weight: 700; color: #fff;
          padding: 2px 4px; border-radius: 3px; white-space: nowrap;
          overflow: hidden; text-overflow: ellipsis;
          text-shadow: 0 1px 1px rgba(0,0,0,.45); }
  .tile .to { font-size: .5rem; opacity: .95; margin-left: 3px; font-weight: 600; }
  .cal-c.has-games { cursor: pointer; }
  .cal-c.has-games:hover { border-color: var(--accent); }
  @media (max-width: 620px) {
    .cal-c { min-height: 46px; padding: 2px; }
    .tile { font-size: .5rem; padding: 1px 2px; }
    .tile .to { display: none; }
    .gnum { font-size: .48rem; }
  }
  /* --- 日付タップの拡大モーダル --- */
  .ov { position: fixed; inset: 0; background: rgba(0,0,0,.62); display: none;
        align-items: center; justify-content: center; padding: 20px; z-index: 50; }
  .ov.show { display: flex; }
  .modal { background: #1b1b2a; border: 1px solid var(--line); border-radius: 14px;
           max-width: 440px; width: 100%; max-height: 86vh; overflow: auto;
           padding: 22px; position: relative; }
  .mx { position: absolute; top: 10px; right: 12px; background: none; border: none;
        color: var(--muted); font-size: 22px; cursor: pointer; line-height: 1; }
  .mtitle { font-size: 1.3rem; font-weight: 800; margin-bottom: 14px; }
  .mgame { background: rgba(255,255,255,.045); border-radius: 10px; padding: 12px 14px;
           margin-bottom: 12px; }
  .mgame.fin { opacity: .55; }
  .mgnum { font-size: .82rem; color: var(--muted); font-weight: 700; margin-bottom: 8px; }
  .mteam { display: flex; align-items: center; gap: 11px; padding: 8px 2px;
           border-bottom: 1px solid var(--line); }
  .mteam:last-child { border-bottom: none; }
  .msw { width: 18px; height: 18px; border-radius: 5px; flex: 0 0 18px; }
  .mnm { font-size: 1.05rem; font-weight: 700; flex: 1; }
  .mow { font-size: .82rem; color: var(--muted); white-space: nowrap; }
  /* 結果（回戦ごとのスコア） */
  .mres { margin-top: 10px; }
  .mround { margin-top: 8px; }
  .mrname { font-size: .78rem; font-weight: 700; color: var(--accent);
            margin-bottom: 3px; }
  .mrrow { display: flex; align-items: center; gap: 8px; padding: 4px 2px;
           border-bottom: 1px dashed rgba(255,255,255,.08); }
  .mrrow:last-child { border-bottom: none; }
  .mrk { width: 16px; text-align: center; color: var(--muted); font-size: .78rem; }
  .mrsw { width: 11px; height: 11px; border-radius: 3px; flex: 0 0 11px; }
  .mrnm { flex: 1; font-size: .92rem; font-weight: 600; }
  .mrtm { font-size: .72rem; color: var(--muted); }
  .mrpt { font-variant-numeric: tabular-nums; font-weight: 800; font-size: .95rem;
          min-width: 54px; text-align: right; }
  .mrpt.pos { color: var(--pos); } .mrpt.neg { color: var(--neg); }
  /* --- 選手ランキング --- */
  .players-card { max-width: 560px; margin: 0 auto; }
  .pteam { font-size: .74rem; color: var(--muted); }
  .pown { font-size: .72rem; margin-left: 6px; font-weight: 700; }
  td.name { line-height: 1.35; }
  /* --- 放送風チームランキング --- */
  .bc { margin: 0; }
  .trow { display: flex; align-items: stretch; margin-bottom: 5px;
          border-radius: 6px; overflow: hidden; background: #191926;
          min-height: 52px; }
  .trow.thead { min-height: 0; background: transparent; color: var(--muted);
                font-size: .72rem; margin-bottom: 6px; }
  .trow.thead .tname { background: transparent !important; align-items: center; }
  .trow.thead .trank { background: transparent !important; }
  .trank { width: 44px; flex: 0 0 44px; display: flex; align-items: center;
           justify-content: center; color: #fff; font-weight: 800;
           font-size: 1.4rem; }
  .tname { flex: 1; min-width: 0; display: flex; flex-direction: column;
           justify-content: center; padding: 6px 12px; }
  .ttop { font-size: .62rem; letter-spacing: .04em; color: #d8d8e4;
          line-height: 1; opacity: .85; }
  .tmain { font-size: 1.15rem; font-weight: 800; color: #fff; line-height: 1.15;
           white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .tpt { flex: 0 0 108px; display: flex; align-items: center;
         justify-content: flex-end; gap: 4px; padding-right: 6px;
         font-size: 1.35rem; font-weight: 800; color: #eef0ff;
         font-variant-numeric: tabular-nums; }
  .tdiff { flex: 0 0 72px; display: flex; align-items: center;
           justify-content: flex-end; color: var(--muted); font-size: .92rem;
           font-variant-numeric: tabular-nums; }
  .tgames { flex: 0 0 74px; display: flex; align-items: baseline;
            justify-content: flex-end; padding-right: 12px; color: #cfcfe0;
            font-size: 1rem; font-variant-numeric: tabular-nums; }
  .tgames span { color: var(--muted); font-size: .7rem; margin-left: 1px; }
  .arw { font-size: .72rem; }
  .arw.up { color: #4caf7d; } .arw.dn { color: #ef5f6b; }
  @media (max-width: 620px) {
    .trank { width: 34px; flex-basis: 34px; font-size: 1.1rem; }
    .tmain { font-size: 1rem; }
    .tpt { flex-basis: 78px; font-size: 1.05rem; }
    .tdiff { flex-basis: 52px; font-size: .78rem; }
    .tgames { flex-basis: 56px; font-size: .82rem; padding-right: 8px; }
  }
"""

_TEMPLATE = (
    """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mリーグ ポイント争奪戦 __SEASON__</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>"""
    + _STYLE
    + """</style>
</head>
<body>
<div class="wrap">
  <h1>🀄 Mリーグ ポイント争奪戦</h1>
  <div class="meta">__SEASON__ ／ __SUBTITLE__</div>
  __NAV__

  <div class="card">
    <h2>👤 個人順位</h2>
    <table>__MEMBER_ROWS__</table>
  </div>

  <div class="card chart-card">
    <h2>🏆 チームランキング</h2>
    <div class="bc">__TEAM_BROADCAST__</div>
  </div>

  <div class="card chart-card">
    <h2>📈 個人ポイント推移</h2>
    <canvas id="trend" height="140"></canvas>
  </div>

  <footer>自動更新 / m-league.jp より集計 ・ 得点はシーズンごとに独立</footer>
</div>

<script>
const DATA = __CHART_DATA__;
let tipOn = false;   // ポイント表(ツールチップ)の表示状態。タップで開閉。
const trend = new Chart(document.getElementById('trend'), {
  type: 'line',
  data: {
    labels: DATA.labels,
    datasets: DATA.datasets.map(d => ({
      label: d.label, data: d.data, borderColor: d.color,
      backgroundColor: d.color, tension: .25, spanGaps: true,
      pointRadius: 3, borderWidth: 2,
    })),
  },
  options: {
    responsive: true,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { labels: { color: '#c8c8dc' } },
      tooltip: { enabled: true },
    },
    // クリック/タップで表示、もう一度で非表示
    onClick: () => {
      tipOn = !tipOn;
      if (!tipOn) {
        trend.setActiveElements([]);
        trend.tooltip.setActiveElements([], { x: 0, y: 0 });
        trend.update();
      }
    },
    scales: {
      x: { ticks: { color: '#9a9ab0' }, grid: { color: '#2c2c3c' } },
      y: { ticks: { color: '#9a9ab0' }, grid: { color: '#2c2c3c' } },
    },
  },
});
</script>
</body>
</html>
"""
)

_ARCHIVE_TEMPLATE = (
    """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mリーグ ポイント争奪戦 アーカイブ</title>
<style>"""
    + _STYLE
    + """</style>
</head>
<body>
<div class="wrap">
  <h1>📚 シーズンアーカイブ</h1>
  <div class="meta">過去シーズンの最終順位</div>
  <nav class="seasons"><a href="index.html">← 今シーズンに戻る</a></nav>
  __CARDS__
  <footer>得点はシーズンごとに独立して集計されます</footer>
</div>
</body>
</html>
"""
)

_PLAYERS_TEMPLATE = (
    """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mリーグ 選手個人ランキング __SEASON__</title>
<style>"""
    + _STYLE
    + """</style>
</head>
<body>
<div class="wrap">
  <h1>🎴 選手個人ランキング</h1>
  <div class="meta">__SEASON__ ／ Mリーグ全選手のポイント順（◆=身内の担当）</div>
  __NAV__
  <div class="card players-card">
    <table>__ROWS__</table>
  </div>
  <footer>m-league.jp より集計</footer>
</div>
</body>
</html>
"""
)

_CAL_TEMPLATE = (
    """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mリーグ 試合日程 __SEASON__</title>
<style>"""
    + _STYLE
    + """</style>
</head>
<body>
<div class="wrap">
  <h1>📅 試合日程</h1>
  <div class="meta">__SEASON__ ／ ✓ = 消化済み ・ タイル色＝チームカラー（1日2試合は第1/第2に分割）</div>
  __NAV__
  __PICKER__
  <div class="legend">__LEGEND__</div>
  <div class="meta" style="margin:-6px 0 14px">📱 日付をタップすると対戦カードを拡大表示</div>
  __MONTHS__
  <footer>m-league.jp より取得</footer>
</div>

<div id="ov" class="ov">
  <div class="modal">
    <button class="mx" aria-label="閉じる">✕</button>
    <div id="mbody"></div>
  </div>
</div>

<script>
const CAL = __CAL_DATA__;
const WD = ['日','月','火','水','木','金','土'];
function openM(iso){
  const games = CAL.days[iso]; if(!games) return;
  const d = new Date(iso + 'T00:00:00');
  const title = d.getFullYear()+'年'+(d.getMonth()+1)+'月'+d.getDate()+'日（'+WD[d.getDay()]+'）';
  let h = '<div class="mtitle">'+title+'</div>';
  games.forEach((g,i)=>{
    h += '<div class="mgame'+(g.finished?' fin':'')+'">';
    const badge = (games.length>1?('第'+(i+1)+'試合'):'') + (g.finished?'　✓ 消化済み':'');
    if(badge.trim()) h += '<div class="mgnum">'+badge+'</div>';
    g.teams.forEach((key,j)=>{
      const t = CAL.teams[key] || {name:(g.raw[j]||''), color:'#555', owner:''};
      h += '<div class="mteam"><span class="msw" style="background:'+t.color+'"></span>'
         + '<span class="mnm">'+t.name+'</span>'
         + (t.owner? '<span class="mow">'+t.owner+'</span>':'') + '</div>';
    });
    if(g.results && g.results.length){
      h += '<div class="mres">';
      g.results.forEach(r=>{
        h += '<div class="mround"><div class="mrname">'+r.round+'</div>';
        r.scores.forEach((s,si)=>{
          const nm=s[0], pt=s[1];
          const pm=CAL.players[nm.replace(/\\s/g,'')]||{short:'',color:'#666'};
          const pc = pt>=0 ? 'pos' : 'neg';
          const sign = pt>0 ? '+'+pt : ''+pt;
          h += '<div class="mrrow"><span class="mrk">'+(si+1)+'</span>'
             + '<span class="mrsw" style="background:'+pm.color+'"></span>'
             + '<span class="mrnm">'+nm+'</span>'
             + '<span class="mrtm">'+pm.short+'</span>'
             + '<span class="mrpt '+pc+'">'+sign+'</span></div>';
        });
        h += '</div>';
      });
      h += '</div>';
    }
    h += '</div>';
  });
  document.getElementById('mbody').innerHTML = h;
  document.getElementById('ov').classList.add('show');
}
function closeM(){ document.getElementById('ov').classList.remove('show'); }
const ov = document.getElementById('ov');
ov.addEventListener('click', e => { if(e.target === ov) closeM(); });
document.querySelector('.mx').addEventListener('click', closeM);
document.addEventListener('keydown', e => { if(e.key === 'Escape') closeM(); });
document.querySelectorAll('.cal-c.has-games').forEach(c => {
  const open = () => openM(c.dataset.date);
  c.addEventListener('click', open);
  c.addEventListener('keydown', e => { if(e.key === 'Enter' || e.key === ' '){ e.preventDefault(); open(); } });
});
</script>
</body>
</html>
"""
)
