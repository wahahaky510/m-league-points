"""LINE送信用の「個人順位（担当順位）」共有カード画像を生成する。

Playwright でカードHTMLをレンダリングしてPNGに切り出し、
docs/line/standings-<date>.png に保存する（GitHub Pagesで公開される）。
LINEにはこの公開URLを画像メッセージとして送る。
"""
from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

from .config import ROOT
from .standings import Snapshot

LINE_DIR = ROOT / "docs" / "line"


def image_filename(snap: Snapshot) -> str:
    return f"standings-{snap.date}.png"


def _card_html(snap: Snapshot) -> str:
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    rows = []
    for i, m in enumerate(snap.members, 1):
        medal = medals.get(i, str(i))
        cls = "pos" if m.point >= 0 else "neg"
        rows.append(
            f'<div class="row"><span class="rk">{medal}</span>'
            f'<span class="nm">{m.name}</span>'
            f'<span class="pt {cls}">{m.point:+.1f}</span></div>'
        )
    rows_html = "\n".join(rows)
    return f"""<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8">
<style>
  * {{ margin:0; box-sizing:border-box; }}
  body {{ background:#0e0e18; }}
  .card {{ width:640px; padding:36px 40px 40px;
    font-family:-apple-system,"Hiragino Kaku Gothic ProN","Meiryo",sans-serif;
    background:linear-gradient(160deg,#1b1b2f,#14141f); color:#e8e8f0; }}
  .ttl {{ font-size:34px; font-weight:800; }}
  .sub {{ color:#9a9ab0; font-size:18px; margin:6px 0 22px; }}
  .hd {{ font-size:20px; font-weight:700; background:#2a2a44; color:#fff;
    padding:8px 14px; border-radius:8px; margin-bottom:10px; }}
  .row {{ display:flex; align-items:center; padding:14px 6px;
    border-bottom:1px solid #2c2c3c; }}
  .rk {{ width:52px; font-size:26px; text-align:center; color:#c8c8dc; }}
  .nm {{ flex:1; font-size:26px; font-weight:700; }}
  .pt {{ font-size:28px; font-weight:800; font-variant-numeric:tabular-nums; }}
  .pos {{ color:#4caf7d; }} .neg {{ color:#ef5f6b; }}
  .ft {{ color:#7a7a90; font-size:15px; margin-top:20px; text-align:right; }}
</style></head><body>
<div class="card" id="card">
  <div class="ttl">🀄 Mリーグ ポイント争奪戦</div>
  <div class="sub">{snap.season} ／ {snap.date} 時点</div>
  <div class="hd">👤 個人順位（担当合計）</div>
  {rows_html}
  <div class="ft">詳しくはダッシュボードへ →</div>
</div>
</body></html>"""


def render_share_image(snap: Snapshot) -> Path:
    """個人順位カードを PNG に出力してパスを返す。"""
    LINE_DIR.mkdir(parents=True, exist_ok=True)
    out = LINE_DIR / image_filename(snap)

    html_path = LINE_DIR / "_card.html"
    html_path.write_text(_card_html(snap), encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 640, "height": 400},
                                device_scale_factor=2)
        page.goto(html_path.as_uri())
        page.wait_for_timeout(300)
        el = page.query_selector("#card")
        el.screenshot(path=str(out))
        browser.close()

    html_path.unlink(missing_ok=True)
    print(f"✅ 共有画像生成: {out.name}")
    return out
