"""Daily Korean proverb message for KakaoTalk's My Chatroom."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from google import genai
from google.genai import types


SEOUL = ZoneInfo("Asia/Seoul")
MAX_MESSAGE_LENGTH = 200
KAKAO_TOKEN_URL = "https://kauth.kakao.com/oauth/token"
KAKAO_SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"


def get_weather() -> str:
    try:
        response = requests.get(
            "https://wttr.in/Seoul?format=%C+%t", timeout=10,
            headers={"User-Agent": "daily-context-proverb/1.0"},
        )
        response.raise_for_status()
        weather = response.text.strip()
        return weather if weather else "상쾌한 아침"
    except requests.RequestException as exc:
        print(f"Weather lookup failed; using default: {exc}")
        return "상쾌한 아침"


def generate_message(date: datetime, weather: str) -> str:
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    prompt = (
        f"오늘 상황: {date.month}월 {date.day}일, {('월요일','화요일','수요일','목요일','금요일','토요일','일요일')[date.weekday()]}, "
        f"서울 날씨는 {weather}입니다.\n\n"
        "이 상황에 맞춰 오늘 하루를 시작하는 데 도움이 되는 성경 잠언 구절 1개와 짧은 묵상 메시지를 작성해 주세요.\n"
        "[오늘의 잠언]\n\"구절 내용\" (잠언 X장 Y절)\n- 응원 메시지"
    )
    system_instruction = (
        "한국어로만 답하세요. 정확히 잠언 구절 하나와 짧은 응원 메시지를 요청 형식으로 작성하세요. "
        "날씨나 요일의 감성을 자연스럽게 반영하세요. 제목, 구절, 인용부호, 출처, 메시지 등 공백과 줄바꿈을 포함한 "
        "전체 응답은 반드시 200자 이내여야 합니다. 설명이나 글자 수 표시는 덧붙이지 마세요."
    )
    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.7,
                    max_output_tokens=300,
                ),
            )
            message = (response.text or "").strip()
            if message and len(message) <= MAX_MESSAGE_LENGTH:
                return message
            print(f"Gemini returned {len(message)} characters; retry {attempt + 1}/1")
        except Exception as exc:  # retry once for API and transient response errors
            print(f"Gemini request failed; retry {attempt + 1}/1: {exc}")
    # A short fallback ensures that a model/API failure does not prevent delivery.
    return "[오늘의 잠언]\n‘마음의 즐거움은 얼굴을 빛나게 한다’ (잠언 15장 13절)\n- 오늘도 기쁨으로 시작해요."


def refresh_kakao_token(refresh_token: str, rest_api_key: str) -> tuple[str, str | None]:
    form = {
        "grant_type": "refresh_token",
        "client_id": rest_api_key,
        "refresh_token": refresh_token,
    }
    client_secret = os.getenv("KAKAO_CLIENT_SECRET")
    if client_secret:
        form["client_secret"] = client_secret
    response = requests.post(KAKAO_TOKEN_URL, data=form, timeout=20)
    if not response.ok:
        error = response.text.replace(refresh_token, "[REDACTED]")
        raise RuntimeError(f"Kakao token refresh failed ({response.status_code}): {error}")
    result = response.json()
    access_token = result.get("access_token")
    if not access_token:
        raise RuntimeError(f"Kakao token refresh response omitted access_token: {result}")
    return access_token, result.get("refresh_token")


def send_kakao_message(access_token: str, message: str) -> None:
    if len(message) > MAX_MESSAGE_LENGTH:
        message = message[:MAX_MESSAGE_LENGTH]
    repository_url = f"https://github.com/{os.getenv('GITHUB_REPOSITORY', '')}".rstrip("/")
    template = {
        "object_type": "text",
        "text": message,
        "link": {"web_url": repository_url, "mobile_web_url": repository_url},
        "button_title": "GitHub",
    }
    response = requests.post(
        KAKAO_SEND_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        data={"template_object": json.dumps(template, ensure_ascii=False)},
        timeout=20,
    )
    if not response.ok:
        error = response.text.replace(access_token, "[REDACTED]")
        raise RuntimeError(f"Kakao message send failed ({response.status_code}): {error}")
    print("KakaoTalk message sent.")


def configured_accounts() -> list[tuple[str, str]]:
    """Prefer individually named family tokens; retain the legacy token list."""
    accounts = [
        (name, os.getenv(secret, "").strip())
        for name, secret in (
            ("본인", "KAKAO_REFRESH_TOKEN_ME"),
            ("배우자", "KAKAO_REFRESH_TOKEN_WIFE"),
            ("딸", "KAKAO_REFRESH_TOKEN_DAUGHTER"),
            ("장인", "KAKAO_REFRESH_TOKEN_FATHER_IN_LAW"),
            ("장모님", "KAKAO_REFRESH_TOKEN_MOTHER_IN_LAW"),
        )
        if os.getenv(secret, "").strip()
    ]
    if accounts:
        return accounts

    # Backward compatibility: JSON array is preferred; comma/newline-separated
    # values are also accepted to make migration from older workflows easier.
    legacy = os.getenv("KAKAO_REFRESH_TOKENS", "").strip()
    if legacy:
        try:
            parsed = json.loads(legacy)
            values = parsed if isinstance(parsed, list) else [parsed]
        except json.JSONDecodeError:
            values = legacy.replace("\n", ",").split(",")
        return [(f"legacy-{index}", str(value).strip()) for index, value in enumerate(values, 1) if str(value).strip()]

    # Also accept the single-account secret used by the initial version.
    single = os.getenv("KAKAO_REFRESH_TOKEN", "").strip()
    return [("본인", single)] if single else []


def main() -> None:
    now = datetime.now(SEOUL)
    weather = get_weather()
    message = generate_message(now, weather)
    print(f"Generated message ({len(message)} chars):\n{message}")

    accounts = configured_accounts()
    if not accounts:
        raise RuntimeError("No Kakao refresh token configured. Add a family token secret.")

    rest_api_key = os.environ["KAKAO_REST_API_KEY"]
    self_access_token: str | None = None
    failures: list[str] = []
    rotated_accounts: list[str] = []

    for account_name, refresh_token in accounts:
        try:
            access_token, rotated_refresh_token = refresh_kakao_token(refresh_token, rest_api_key)
            if account_name == "본인":
                self_access_token = access_token
            if rotated_refresh_token:
                rotated_accounts.append(account_name)
                print(f"WARNING: Kakao returned a rotated refresh token for {account_name}; update its GitHub Secret manually.")
            send_kakao_message(access_token, message)
            print(f"Proverb sent to {account_name} account.")
        except Exception as exc:
            # Continue so one expired family token cannot block other recipients.
            failures.append(account_name)
            print(f"ERROR: Kakao delivery failed for {account_name}: {exc}", file=sys.stderr)

    notices = []
    if rotated_accounts:
        notices.append(
            f"[토큰 갱신 안내] {', '.join(rotated_accounts)} 계정의 Kakao refresh token이 교체되었습니다. "
            "해당 GitHub Secret을 새 토큰으로 수동 갱신해 주세요. 토큰 값은 로그에 표시하지 않았습니다."
        )
    if failures:
        notices.append(f"[발송 오류 안내] 다음 계정의 잠언 메시지 발송에 실패했습니다: {', '.join(failures)}. Actions 로그를 확인해 주세요.")
    if notices and self_access_token:
        for notice in notices:
            try:
                send_kakao_message(self_access_token, notice)
            except Exception as exc:
                print(f"Could not send technical notice to own account: {exc}", file=sys.stderr)
    elif notices:
        print("WARNING: Could not send technical notice to own account because the own account token was unavailable.")

    if failures:
        raise RuntimeError(f"Kakao delivery failed for {len(failures)} account(s): {', '.join(failures)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Daily proverb workflow failed: {exc}", file=sys.stderr)
        raise
