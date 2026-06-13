from __future__ import annotations

import json
import logging
from pathlib import Path

import gspread
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials as UserCredentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def load_google_credentials(creds_path: Path):
    with creds_path.open(encoding="utf-8") as file:
        data = json.load(file)

    if data.get("type") == "service_account":
        return ServiceAccountCredentials.from_service_account_file(str(creds_path), scopes=SCOPES)

    if "refresh_token" in data or "token" in data:
        credentials = UserCredentials.from_authorized_user_file(str(creds_path), scopes=SCOPES)
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            data["token"] = credentials.token
            data["expiry"] = credentials.expiry.isoformat() if credentials.expiry else None
            with creds_path.open("w", encoding="utf-8") as file:
                json.dump(data, file, indent=2)
            logger.info("Google OAuth токен обновлён")
        return credentials

    raise ValueError(
        "Неподдерживаемый формат credentials.json. "
        "Нужен JSON сервисного аккаунта (type: service_account) "
        "или OAuth-токен (token + refresh_token)."
    )


def open_spreadsheet(credentials_file: str, spreadsheet_id: str):
    creds_path = Path(credentials_file)
    if not creds_path.exists():
        raise FileNotFoundError(f"Файл credentials не найден: {creds_path}")

    credentials = load_google_credentials(creds_path)
    client = gspread.authorize(credentials)
    return client.open_by_key(spreadsheet_id)
