"""Daily Korean proverb message for KakaoTalk's My Chatroom."""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import date as CalendarDate, datetime
from pathlib import Path
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


def load_proverbs() -> list[dict[str, object]]:
    path = Path(__file__).with_name("proverbs.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    verses = data.get("verses")
    if not isinstance(verses, list) or not verses:
        raise RuntimeError("proverbs.json must contain a non-empty verses list.")

    seen: set[tuple[int, int]] = set()
    for item in verses:
        if not isinstance(item, dict):
            raise RuntimeError("Each proverb entry must be a JSON object.")
        chapter, verse, text = item.get("chapter"), item.get("verse"), item.get("text")
        if not isinstance(chapter, int) or not 1 <= chapter <= 31:
            raise RuntimeError(f"Invalid Proverbs chapter in proverbs.json: {chapter}")
        if not isinstance(verse, int) or verse < 1 or not isinstance(text, str) or not text.strip():
            raise RuntimeError(f"Invalid Proverbs verse entry: {item}")
        reference = (chapter, verse)
        if reference in seen:
            raise RuntimeError(f"Duplicate Proverbs reference in proverbs.json: {chapter}:{verse}")
        seen.add(reference)
    return verses


def select_proverb(date: datetime) -> dict[str, object]:
    verses = load_proverbs()
    day_number = (date.date() - CalendarDate(2026, 1, 1)).days
    return verses[day_number % len(verses)]


def compose_message(proverb: dict[str, object], reflection: str) -> str:
    message = (
        "[오늘의 잠언]\n"
        f'"{proverb["text"]}" (잠언 {proverb["chapter"]}장 {proverb["verse"]}절)\n'
        f"- {reflection}"
    )
    if len(message) > MAX_MESSAGE_LENGTH:
        raise RuntimeError(f"Composed proverb message exceeds {MAX_MESSAGE_LENGTH} characters.")
    return message


def generate_reflection(date: datetime, weather: str, proverb: dict[str, object]) -> str:
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    reference = f"잠언 {proverb['chapter']}장 {proverb['verse']}절"
    quoted_verse = str(proverb["text"])
    reflection_prefix = f'[오늘의 잠언]\n"{quoted_verse}" ({reference})\n- '
    max_reflection_length = MAX_MESSAGE_LENGTH - len(reflection_prefix)
    prompt = (
        f"오늘 상황: {date.month}월 {date.day}일, {('월요일','화요일','수요일','목요일','금요일','토요일','일요일')[date.weekday()]}, "
        f"서울 날씨는 {weather}입니다.\n"
        f"오늘의 잠언은 {reference}입니다. 본문은 다음과 같습니다: {quoted_verse}\n\n"
        "이 구절을 바탕으로 오늘 하루를 시작하는 데 도움이 되는 짧은 묵상과 응원 문장 하나만 작성해 주세요. "
        "성경 구절이나 장절을 다시 쓰지 마세요."
    )
    system_instruction = (
        "한국어로 묵상과 응원 문장 하나만 답하세요. 날씨나 요일을 자연스럽게 반영하되 제공된 성경 본문과 장절은 "
        "반복하거나 바꾸지 마세요. 제목, 인용구, 장절, 글자 수 설명은 출력하지 마세요. "
        f"응답은 공백 포함 {max_reflection_length}자 이내의 한 문장으로 작성하세요."
    )
    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    thinking_config=types.ThinkingConfig(thinking_level="low"),
                    max_output_tokens=512,
                ),
            )
            reflection = " ".join((response.text or "").split()).strip(" \"'“”‘’*-")
            candidate = response.candidates[0] if response.candidates else None
            finish_reason = str(getattr(candidate, "finish_reason", "")).upper()
            hit_token_limit = "MAX_TOKENS" in finish_reason
            contains_new_reference = bool(re.search(r"잠언\s*\d+\s*장\s*\d+\s*절", reflection))
            if reflection and len(reflection) <= max_reflection_length and not contains_new_reference and not hit_token_limit:
                return reflection
            print(
                f"Gemini returned an incomplete/invalid reflection ({len(reflection)} chars); "
                f"retry {attempt + 1}/1"
            )
        except Exception as exc:  # retry once for API and transient response errors
            print(f"Gemini request failed; retry {attempt + 1}/1: {exc}")
    return "오늘도 지혜를 따라 한 걸음씩 나아가요."


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
    family = (
        ("본인", "KAKAO_REFRESH_TOKEN_ME", None),
        ("배우자", "KAKAO_REFRESH_TOKEN_WIFE", None),
        ("딸", "KAKAO_REFRESH_TOKEN_DAUGHTER", None),
        ("장인", "KAKAO_REFRESH_TOKEN_FATHER_IN_LAW", "KAKAO_SKIP_FATHER_IN_LAW"),
        ("장모님", "KAKAO_REFRESH_TOKEN_MOTHER_IN_LAW", "KAKAO_SKIP_MOTHER_IN_LAW"),
    )
    family_values = [(name, secret, skip_env, os.getenv(secret, "").strip()) for name, secret, skip_env in family]
    if any(value for _, _, _, value in family_values):
        accounts = []
        for name, _, skip_env, token in family_values:
            if skip_env and os.getenv(skip_env, "").strip().lower() in {"1", "true", "yes", "on"}:
                print(f"Skipping {name} account (temporarily disabled).")
                continue
            if token:
                accounts.append((name, token))
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
    proverb = select_proverb(now)
    reflection = generate_reflection(now, weather, proverb)
    message = compose_message(proverb, reflection)
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
