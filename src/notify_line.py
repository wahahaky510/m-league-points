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


def build_messages(settings: Settings, snap: Snapshot) -> list[dict]:
    img = _image_url(settings, snap)
    top = snap.members[0]
    text = (
        f"🀄 Mリーグ ポイント争奪戦\n"
        f"{snap.season} ／ {snap.date} 時点\n"
        f"個人順位トップ：{top.name}（{top.point:+.1f}）\n\n"
        f"📊 ダッシュボード\n{settings.dashboard_url}"
    )
    return [
        {"type": "text", "text": text},
        {"type": "image", "originalContentUrl": img, "previewImageUrl": img},
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
