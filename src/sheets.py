"""Google Sheets の「順位表」シートを毎回クリーンに描き直す。

去年は行番号・XLOOKUP・背景色コピーが絡み合っていたが、
今年は Snapshot を素直に書き出すだけにする（履歴は JSON 側が持つ）。
書き込み先は専用シート「順位表」なので、他のシートは触らない。
"""
from __future__ import annotations

from googleapiclient.discovery import build

from .config import Settings, build_google_credentials
from .standings import Snapshot

SHEET_NAME = "順位表"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

_HEADER_BG = {"red": 0.106, "green": 0.106, "blue": 0.184}  # #1B1B2F
_HEADER_FG = {"red": 1, "green": 1, "blue": 1}


def _service(settings: Settings):
    creds = build_google_credentials(settings, SCOPES)
    return build("sheets", "v4", credentials=creds)


def _ensure_sheet(service, spreadsheet_id: str) -> int:
    meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    for sh in meta["sheets"]:
        if sh["properties"]["title"] == SHEET_NAME:
            return sh["properties"]["sheetId"]
    resp = service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": SHEET_NAME}}}]},
    ).execute()
    return resp["replies"][0]["addSheet"]["properties"]["sheetId"]


def update_standings_sheet(settings: Settings, snap: Snapshot) -> None:
    """順位表シートをスナップショットで丸ごと更新する。"""
    service = _service(settings)
    sheet_id = _ensure_sheet(service, settings.spreadsheet_id)

    # --- 値を組み立て（A列: 個人順位ブロック / D列: チーム順位ブロック） ---
    values: list[list[object]] = []
    values.append([f"Mリーグ ポイント争奪戦  {snap.season}", "", "", f"更新: {snap.date}", "", ""])
    values.append(["", "", "", "", "", ""])
    values.append(["👤 個人順位", "", "", "🏆 チーム順位", "", ""])
    values.append(["順位", "メンバー", "ポイント", "順位", "チーム", "ポイント（担当）"])

    n = max(len(snap.members), len(snap.teams))
    for i in range(n):
        row: list[object] = []
        if i < len(snap.members):
            m = snap.members[i]
            row += [i + 1, m.name, m.point]
        else:
            row += ["", "", ""]
        if i < len(snap.teams):
            t = snap.teams[i]
            row += [i + 1, f"{t.team}（{t.owner}）", t.point]
        else:
            row += ["", "", ""]
        values.append(row)

    end_row = len(values)
    body = {"values": values}

    # クリアしてから書き込み
    service.spreadsheets().values().clear(
        spreadsheetId=settings.spreadsheet_id, range=f"{SHEET_NAME}!A1:F200"
    ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=settings.spreadsheet_id,
        range=f"{SHEET_NAME}!A1",
        valueInputOption="USER_ENTERED",
        body=body,
    ).execute()

    # --- 書式（タイトル・見出し・ヘッダ行） ---
    requests = [
        # タイトル行
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1,
                          "startColumnIndex": 0, "endColumnIndex": 6},
                "cell": {"userEnteredFormat": {
                    "textFormat": {"bold": True, "fontSize": 12}}},
                "fields": "userEnteredFormat.textFormat",
            }
        },
        # セクション見出し行（3行目）
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 2, "endRowIndex": 3,
                          "startColumnIndex": 0, "endColumnIndex": 6},
                "cell": {"userEnteredFormat": {
                    "textFormat": {"bold": True}}},
                "fields": "userEnteredFormat.textFormat",
            }
        },
        # ヘッダ行（4行目）に背景色
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 3, "endRowIndex": 4,
                          "startColumnIndex": 0, "endColumnIndex": 6},
                "cell": {"userEnteredFormat": {
                    "backgroundColor": _HEADER_BG,
                    "textFormat": {"foregroundColor": _HEADER_FG, "bold": True}}},
                "fields": "userEnteredFormat(backgroundColor,textFormat)",
            }
        },
        # 列幅
        {
            "updateDimensionProperties": {
                "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                          "startIndex": 1, "endIndex": 2},
                "properties": {"pixelSize": 130}, "fields": "pixelSize",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                          "startIndex": 4, "endIndex": 5},
                "properties": {"pixelSize": 220}, "fields": "pixelSize",
            }
        },
    ]
    service.spreadsheets().batchUpdate(
        spreadsheetId=settings.spreadsheet_id, body={"requests": requests}
    ).execute()

    print(f"✅ 順位表シート更新完了（{end_row}行）")
