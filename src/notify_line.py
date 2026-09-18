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

import sys
import time

import requests

from .config import Settings, load_settings
from .share_image import image_filename
from .standings import Snapshot, load_latest

PUSH_ENDPOINT = "https://api.line.me/v2/bot/message/push"


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


def build_messages(settings: Settings, snap: Snapshot) -> list[dict]:
    import os

    img = _image_url(settings, snap)
    members = snap.members
    top = members[0]
    zako = members[-2] if len(members) >= 2 else None
    kuso = members[-1] if len(members) >= 1 else None

    def line(label: str, m) -> dict:
        return {"type": "text", "text": f"{label}：{m.name}（{m.point:+.1f}点）",
                "size": "sm", "color": "#333333", "wrap": True}

    body_contents = [
        {"type": "text", "text": "🀄 Mリーグ ポイント争奪戦",
         "weight": "bold", "size": "md", "color": "#111111"},
        {"type": "text", "text": f"{snap.season}シーズン ／ {_jp_date(snap.date)}時点",
         "size": "xs", "color": "#999999"},
        {"type": "separator", "margin": "md"},
    ]
    # テスト送信などの先頭ラベル
    prefix = os.getenv("LINE_MESSAGE_PREFIX", "").strip()
    if prefix:
        body_contents.insert(0, {"type": "text", "text": prefix, "weight": "bold",
                                 "size": "sm", "color": "#C62828", "wrap": True})
    if top:
        body_contents.append(line("トップ", top))
    if zako:
        body_contents.append(line("雑魚", zako))
    if kuso:
        body_contents.append(line("クソ雑魚", kuso))

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
    flex = {"type": "flex", "altText": f"Mリーグ順位 {_jp_date(snap.date)}：トップ "
            f"{top.name}", "contents": bubble}

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

    headers = {
        "Authorization": f"Bearer {settings.line_channel_access_token}",
        "Content-Type": "application/json",
    }
    payload = {"to": settings.line_target_id, "messages": build_messages(settings, snap)}
    resp = requests.post(PUSH_ENDPOINT, headers=headers, json=payload, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"LINE送信エラー: {resp.status_code} {resp.text}")
    print("✅ LINE送信完了（個人順位スクショ＋URL）")


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
