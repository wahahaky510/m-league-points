"""LINE Messaging API へ「個人順位のスクショ＋ダッシュボードURL」を送る。

去年は message.py（テキスト）と image-message.py（座標スクショ）に分かれ、
Google Drive 経由で画像を公開していた。今年は:
  1. 個人順位カード画像を生成（share_image）
  2. GitHub Pages に公開（Actions が docs/ を push してデプロイ）
  3. 公開URLが見えるようになってから、画像＋テキストを push
という流れにする。ローカル実行では公開URLが無いので送信はスキップする。

グループID宛の push なので、グループ全員に表示される。
"""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

import requests

from .config import ROOT, Settings, load_settings
from .share_image import image_filename
from .standings import Snapshot, load_latest

PUSH_ENDPOINT = "https://api.line.me/v2/bot/message/push"

# クソ雑魚（最下位）へのあおり文。{name}=名前 / {pt}=符号付きポイント（例 -204.9）
# 毎週この中からランダムで1つ、シーズン中は被らないように出す。
TAUNTS = [
    "🀄 今週のクソ雑魚は {name}（{pt}）。期待を裏切らないマイナスっぷり、お見事。",
    "🀄 速報：クソ雑魚{name} が沈んでいます（{pt}）。海底より深い。",
    "🀄 クソ雑魚{name}（{pt}）、君のためにこのリーグがある。みんなの心の支えだ。",
    "🀄 クソ雑魚{name}。{pt}って、わざとやってる？才能を感じる。",
    "🀄 クソ雑魚{name}（{pt}）。安定の底。地球の中心はここにあった。",
    "🀄 クソ雑魚はこの男！ {name}（{pt}）。マイナスの美学、極めし者。",
    "🀄 クソ雑魚{name}、{pt}。ありがとう。",
    "🀄 クソ雑魚{name}（{pt}）に拍手。誰かが最下位をやらねばならない、その尊い犠牲。",
    "🀄 クソ雑魚{name}（{pt}）。放銃センスだけは全国区。",
    "🀄 発掘調査の結果、最深部からクソ雑魚 {name}（{pt}）が発見されました。",
    "🀄 クソ雑魚{name}、{pt}。この人がいるだけでみんな安心できる。ありがとう。",
    "🀄 クソ雑魚認定書\n{name} くん（{pt}）\nあなたは今週、卓の最下位という重責を\n見事に全うされました。\nその献身を讃え、ここにクソ雑魚として認定します。",
    "🀄 クソ雑魚{name}（{pt}）。チームが悪いんじゃない、たぶん君だ。",
    "🀄 クソ雑魚{name}、{pt}。マイナスを彫り続ける職人。",
    "🀄 クソ雑魚の椅子、温めているのは {name}（{pt}）くん。座り心地はどう？",
    "🀄 クソ雑魚{name}（{pt}）。この点数を出すのって、すごいな。",
    "🀄 悲報：{name}がクソ雑魚ですwwwwww {pt}ってwwwwww",
    "🀄 クソ雑魚{name}（{pt}）笑",
    "🀄 本日の底辺代表 {name}（{pt}）。堂々のマイナス、風格すら漂う。",
    "🀄 クソ雑魚 {name}、{pt}。プラスってどんな味だったか覚えてる？",
    "🀄 クソ雑魚 {name}（{pt}）。もはやマイナスが定位置。おつかれさま。",
    "🀄 クソ雑魚 {name}（{pt}）。今日も麻雀の神に嫌われている。",
    "🀄 クソ雑魚 {name}、{pt}。その沈みっぷり、もう芸術の域。",
    "🀄 クソ雑魚 {name}（{pt}）。放銃で世界を救う！",
    "🀄 クソ雑魚 {name}、{pt}。この人のおかげでみんなが輝ける。",
    "🀄 クソ雑魚 {name}（{pt}）。ラス回避、という概念を知らない男。",
    "🀄 クソ雑魚 {name}（{pt}）。放銃と親被りとときどきピンヅモ。",
    "🀄 クソ雑魚 {name}、{pt}。トップの背中が地平線の彼方に消えていく。",
    "🀄 クソ雑魚 {name}（{pt}）。もうあきらめろ。",
    "🀄 クソ雑魚 {name}、{pt}。ここまで負けると逆に清々しい。天晴れ。",
    "🀄 クソ雑魚 {name}（{pt}）。支払いできますか～？",
    "🀄 クソ雑魚 {name}（{pt}）。チームのせいにするな。お前の実力だ。",
    "🀄 クソ雑魚 {name}、{pt}。マイナスの伸びしろだけは無限大。",
    "🀄 クソ雑魚 {name}（{pt}）。息してる？",
    "🀄 クソ雑魚 {name}、{pt}。底が抜けてる。地下何階まで行く気だ。",
]


def _used_path(season: str) -> Path:
    return ROOT / "data" / "seasons" / season / "taunts_used.json"


def _load_used(season: str) -> list[int]:
    f = _used_path(season)
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return []


def choose_taunt(season: str, kuso) -> tuple[int, str]:
    """未使用のあおり文からランダムに1つ選ぶ（全部使い切ったら一巡してリセット）。

    戻り値: (インデックス, 整形済みテキスト)。ここでは used を保存しない
    （送信成功後に persist_taunt で確定する）。
    """
    used = set(_load_used(season))
    available = [i for i in range(len(TAUNTS)) if i not in used]
    if not available:  # 全部使い切ったら新しい一巡
        available = list(range(len(TAUNTS)))
    idx = random.choice(available)
    pt = f"{kuso.point:+.1f}"
    return idx, TAUNTS[idx].format(name=kuso.name, pt=pt)


def persist_taunt(season: str, idx: int) -> None:
    """送信できたあおり文のインデックスを使用済みに記録する。"""
    used = _load_used(season)
    if len(used) >= len(TAUNTS):
        used = []  # 一巡完了 → リセットして今回分から新サイクル
    if idx not in used:
        used.append(idx)
    p = _used_path(season)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(used, ensure_ascii=False), encoding="utf-8")


def _image_url(settings: Settings, snap: Snapshot) -> str:
    base = settings.dashboard_url.rstrip("/")
    return f"{base}/line/{image_filename(snap)}"


def _wait_until_public(url: str, timeout: int = 240, interval: int = 10) -> bool:
    """GitHub Pages のデプロイ反映を待つ（画像URLが200を返すまで）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.head(url, timeout=15, allow_redirects=True)
            if r.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(interval)
    return False


def _jp_date(iso: str) -> str:
    """"2026-09-18" -> "9/18"（ISO表記のままだと日付が自動リンク化されるため）。"""
    try:
        _y, m, d = iso.split("-")
        return f"{int(m)}/{int(d)}"
    except ValueError:
        return iso


def build_messages(settings: Settings, snap: Snapshot, taunt_text: str) -> list[dict]:
    """画像＋あおり一言＋Dashboardボタン。順位詳細は画像で分かるので載せない。"""
    import os

    img = _image_url(settings, snap)
    body_contents = []
    # テスト送信などの先頭ラベル
    prefix = os.getenv("LINE_MESSAGE_PREFIX", "").strip()
    if prefix:
        body_contents.append({"type": "text", "text": prefix, "weight": "bold",
                              "size": "sm", "color": "#C62828", "wrap": True})
    body_contents.append({"type": "text", "text": taunt_text, "size": "md",
                          "weight": "bold", "color": "#111111", "wrap": True})

    bubble = {
        "type": "bubble",
        "body": {"type": "box", "layout": "vertical", "spacing": "sm",
                 "contents": body_contents},
        "footer": {"type": "box", "layout": "vertical", "contents": [{
            "type": "button", "style": "primary", "color": "#1B1B2F", "height": "sm",
            "action": {"type": "uri", "label": "Dashboard",
                       "uri": settings.dashboard_url},
        }]},
    }
    alt = taunt_text.replace("\n", " ")[:60]
    flex = {"type": "flex", "altText": alt, "contents": bubble}

    return [
        {"type": "image", "originalContentUrl": img, "previewImageUrl": img},
        flex,
    ]


def send(settings: Settings, snap: Snapshot, wait_public: bool = True) -> None:
    if not settings.dashboard_url:
        raise RuntimeError(
            "DASHBOARD_URL が未設定です。画像の公開URLを作れないため送信できません。"
        )
    img = _image_url(settings, snap)
    if wait_public:
        print(f"画像の公開待ち: {img}")
        if not _wait_until_public(img):
            raise RuntimeError(f"画像URLが公開されませんでした: {img}")

    kuso = snap.members[-1] if snap.members else None
    idx, taunt_text = choose_taunt(snap.season, kuso) if kuso else (-1, "🀄 Mリーグ ポイント争奪戦")

    headers = {
        "Authorization": f"Bearer {settings.line_channel_access_token}",
        "Content-Type": "application/json",
    }
    payload = {"to": settings.line_target_id,
               "messages": build_messages(settings, snap, taunt_text)}
    resp = requests.post(PUSH_ENDPOINT, headers=headers, json=payload, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"LINE送信エラー: {resp.status_code} {resp.text}")
    if idx >= 0:
        persist_taunt(snap.season, idx)  # 送信成功後に使用済み確定
    print(f"✅ LINE送信完了（あおり文 #{idx + 1}）")


def main(argv: list[str] | None = None) -> int:
    """公開済みの画像を参照して LINE 送信する（Actions のデプロイ後ステップ用）。

    --no-wait で公開待ちをスキップ（既に公開済みの場合）。
    """
    import argparse

    parser = argparse.ArgumentParser(description="LINEに個人順位スクショ＋URLを送信")
    parser.add_argument("--no-wait", action="store_true", help="画像の公開待ちをしない")
    args = parser.parse_args(argv)

    settings = load_settings(require_line=True)
    snap = load_latest()
    if snap is None:
        print("latest.json がありません。先に集計を実行してください。")
        return 1
    send(settings, snap, wait_public=not args.no_wait)
    return 0


if __name__ == "__main__":
    sys.exit(main())
