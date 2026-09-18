"""設定と秘密情報の一元管理。

去年は各スクリプトにトークンやIDがベタ書きされていたが、
今年は環境変数（ローカルは .env / Actions は Secrets）経由に統一する。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

# リポジトリのルート（このファイルは src/ にある）
ROOT = Path(__file__).resolve().parent.parent

# ローカル実行時は .env を読み込む（Actions では実環境変数が使われる）
load_dotenv(ROOT / ".env")

STATS_URL = "https://m-league.jp/stats"


@dataclass
class Assignment:
    team: str
    owner: str
    short: str = ""
    color: str = "#888888"
    top: str = ""
    main: str = ""


@dataclass
class TeamsConfig:
    """config/teams.yaml の内容。"""

    season: str
    total_point_label: str
    members: list[str]
    assignments: list[Assignment] = field(default_factory=list)
    regular_season_end_month: int = 3
    games_total: int = 120

    @property
    def owner_by_team(self) -> dict[str, str]:
        return {a.team: a.owner for a in self.assignments}

    @property
    def start_year(self) -> int:
        """"2026-27" -> 2026。"""
        return int(self.season.split("-")[0])

    @property
    def regular_season_end(self):
        """レギュラーシーズン最終日（終了月の月末）を date で返す。"""
        import calendar as _cal
        from datetime import date as _date

        month = self.regular_season_end_month
        year = self.start_year if month >= 9 else self.start_year + 1
        last_day = _cal.monthrange(year, month)[1]
        return _date(year, month, last_day)

    def in_regular_season(self, on=None) -> bool:
        """指定日（既定は今日）がレギュラーシーズン内か。"""
        from datetime import date as _date

        on = on or _date.today()
        start = _date(self.start_year, 9, 1)
        return start <= on <= self.regular_season_end

    def in_regular_season_month(self, month: int) -> bool:
        """その月がレギュラーシーズンの対象月か（9〜12月＋1〜終了月）。"""
        end = self.regular_season_end_month
        return month >= 9 or month <= end


@dataclass
class Settings:
    spreadsheet_id: str
    line_channel_access_token: str
    line_target_id: str
    dashboard_url: str
    teams: TeamsConfig
    credentials_file: str
    credentials_json: str

    @property
    def sheet_url(self) -> str:
        return (
            f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}"
            "/edit?usp=sharing"
        )


def _require(name: str) -> str:
    val = os.getenv(name, "").strip()
    if not val:
        raise RuntimeError(
            f"環境変数 {name} が未設定です。.env または GitHub Secrets を確認してください。"
        )
    return val


def load_teams_config(path: Path | None = None) -> TeamsConfig:
    path = path or (ROOT / "config" / "teams.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    members = [m["name"] for m in data.get("members", [])]
    assignments = [
        Assignment(
            team=a["team"], owner=a["owner"], short=a.get("short", ""),
            color=a.get("color", "#888888"), top=a.get("top", ""), main=a.get("main", ""),
        )
        for a in data.get("assignments", [])
    ]
    return TeamsConfig(
        season=data["season"],
        total_point_label=data.get("total_point_label", "合計ポイント"),
        members=members,
        assignments=assignments,
        regular_season_end_month=int(data.get("regular_season_end_month", 3)),
        games_total=int(data.get("games_total", 120)),
    )


def load_settings(require_line: bool = True) -> Settings:
    """環境変数と teams.yaml から設定を組み立てる。

    require_line: LINE送信を行わない処理（ダッシュボード生成のみ等）では
    False にしてトークン未設定でも動かせるようにする。
    """
    return Settings(
        spreadsheet_id=_require("SPREADSHEET_ID"),
        line_channel_access_token=(
            _require("LINE_CHANNEL_ACCESS_TOKEN")
            if require_line
            else os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
        ),
        line_target_id=(
            _require("LINE_TARGET_ID") if require_line else os.getenv("LINE_TARGET_ID", "")
        ),
        dashboard_url=os.getenv("DASHBOARD_URL", "").strip(),
        teams=load_teams_config(),
        credentials_file=os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json"),
        credentials_json=os.getenv("GOOGLE_CREDENTIALS_JSON", ""),
    )


def build_google_credentials(settings: Settings, scopes: list[str]):
    """サービスアカウント認証情報を生成する。

    Actions では credentials.json をリポに置けないので、
    GOOGLE_CREDENTIALS_JSON に丸ごと入れておけばそちらを優先して使う。
    """
    from google.oauth2.service_account import Credentials

    if settings.credentials_json:
        info = json.loads(settings.credentials_json)
        return Credentials.from_service_account_info(info, scopes=scopes)

    cred_path = Path(settings.credentials_file)
    if not cred_path.is_absolute():
        cred_path = ROOT / cred_path
    return Credentials.from_service_account_file(str(cred_path), scopes=scopes)
