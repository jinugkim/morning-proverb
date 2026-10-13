# Daily Context-Aware Proverb Bot

매일 오전 7시(한국 시간)에 서울 날씨와 날짜를 반영한 잠언 구절 및 짧은 묵상을 생성해 카카오톡 **나에게 보내기**로 전달합니다. Gemini 응답은 공백과 줄바꿈을 포함해 200자 이내인지 검사합니다.

## 동작

1. GitHub Actions가 매일 22:00 UTC (다음 날 07:00 KST)에 실행됩니다. `workflow_dispatch`로 수동 실행도 할 수 있습니다.
2. `wttr.in`에서 서울 날씨를 조회합니다. 조회가 실패하면 `상쾌한 아침`을 사용합니다.
3. `proverbs.json`에서 날짜에 따라 고정 잠언 구절을 고르고, `gemini-3.8-flash`는 날씨·요일을 반영한 묵상 한 문장만 생성합니다. 낮은 thinking level을 사용하고, API 실패나 너무 긴 묵상은 한 번 재시도한 뒤 짧은 기본 묵상을 사용합니다.
4. 본인·배우자·딸·장인·장모님의 refresh token으로 각각 access token을 발급합니다.
5. 각 토큰으로 Kakao 기본 텍스트 템플릿 API를 호출해 해당 계정의 나와의 채팅으로 보냅니다. 친구 목록이나 친구 UUID, 친구 메시지 API는 사용하지 않습니다.
6. 한 계정의 실패가 다른 계정 발송을 중단하지 않습니다. 일부 계정이 실패하면 Actions 실행도 실패로 표시합니다.
7. Kakao가 새 refresh token을 반환하면 해당 계정 이름만 로그와 본인 계정의 기술 안내에 표시합니다. Secret은 자동 수정하지 않으므로 새 토큰으로 직접 교체해야 합니다. 토큰 값은 로그나 안내에 출력하지 않습니다.

## 잠언 구절과 번역본

`proverbs.json`에는 공개 도메인으로 배포되는 Korean Bible 1910 (1911년판)의 잠언 중 확인한 28개 구절을 저장했습니다. 각 구절의 장절과 원문 페이지 주소도 데이터에 함께 기록합니다. 구절은 KST 날짜를 기준으로 하루에 하나씩 순환하므로 같은 날 재실행해도 같은 구절이 선택됩니다. 이 번역본은 개역개정판보다 옛 표현을 사용합니다. 구절 본문과 장절은 목록에서 고정하고, Gemini는 묵상 문장만 생성합니다. Google의 구조화 출력도 데이터의 의미적 정확성까지 보장하지 않기 때문에, 성경 인용을 모델에서 분리했습니다.

## GitHub 설정

저장소의 **Settings → Secrets and variables → Actions**에서 다음 Repository secrets를 등록하세요.

| Secret | 설명 |
| --- | --- |
| `GEMINI_API_KEY` | Google AI Studio API 키 |
| `KAKAO_REST_API_KEY` | Kakao 앱의 REST API 키 |
| `KAKAO_REFRESH_TOKEN_ME` | 본인 Kakao 계정에서 발급한 refresh token |
| `KAKAO_REFRESH_TOKEN_WIFE` | 배우자 Kakao 계정에서 발급한 refresh token |
| `KAKAO_REFRESH_TOKEN_DAUGHTER` | 딸 Kakao 계정에서 발급한 refresh token |
| `KAKAO_REFRESH_TOKEN_FATHER_IN_LAW` | 장인 Kakao 계정에서 발급한 refresh token |
| `KAKAO_REFRESH_TOKEN_MOTHER_IN_LAW` | 장모님 Kakao 계정에서 발급한 refresh token |
| `KAKAO_CLIENT_SECRET` | Kakao REST API 키의 Client Secret 값. 기본 활성화되어 있으므로, 명시적으로 끈 경우가 아니라면 등록 |

가족별 Secret이 하나라도 설정되면 위에 설정한 계정 Secret만 처리합니다. 가족별 Secret이 모두 없으면 호환용 `KAKAO_REFRESH_TOKENS` Secret(JSON 배열 또는 쉼표/줄바꿈 구분)을 사용하고, 그것도 없으면 구버전 단일 `KAKAO_REFRESH_TOKEN`을 사용합니다. 가족별 구성이 일부만 되어 있어도 설정된 계정만 대상으로 합니다.

현재 장인·장모님 계정은 토큰 문제로 발송을 잠시 중지했습니다. 워크플로에서 `KAKAO_SKIP_FATHER_IN_LAW`와 `KAKAO_SKIP_MOTHER_IN_LAW`가 `true`로 설정되어 있어 해당 토큰이 등록되어 있어도 요청하지 않습니다. 재개할 때 두 값을 `false`로 바꾸고 유효한 가족별 Secret을 등록하세요.

각 가족 구성원은 본인 카카오 계정으로 로그인하고 `talk_message` 동의를 완료한 뒤 자기 refresh token을 발급해야 합니다. Kakao Developers에서 Kakao Login 및 Kakao Talk Message 사용도 설정해야 합니다. 모든 계정 토큰은 같은 Kakao 앱의 REST API 키와 (사용 설정 시) Client Secret으로 발급해야 합니다. `expired_or_invalid_refresh_token` 또는 `KOE322`가 나오면 해당 계정의 refresh token이 만료·무효이거나 비어 있는 것이므로, 그 계정으로 인가 코드를 통해 토큰을 다시 발급하고 대응하는 Secret을 교체하세요. 토큰 발급/갱신에는 Kakao 앱 설정에서 Client Secret이 켜져 있으면 `KAKAO_CLIENT_SECRET`도 필요합니다. 한 계정의 오류는 나머지 계정 발송을 중단하지 않습니다.

### 가족별 refresh token 발급 도구

`get_tokens.py`는 로컬 컴퓨터에서만 실행하는 OAuth 도구입니다. Kakao Developers의 **앱 설정 → 플랫폼 키 → REST API 키 → Redirect URI**에 아래 주소를 등록하세요. 도구는 `127.0.0.1`에서만 실행되고, 토큰은 브라우저 결과 화면에만 표시됩니다.

```text
http://127.0.0.1:5000/oauth
```

저장소 폴더에서 Flask 의존성을 설치하고 키를 입력해 실행합니다. macOS 기본 zsh에서는 `read -s`로 입력하면 키가 명령 기록에 남지 않습니다. Client Secret을 앱에서 활성화한 경우에만 입력하세요.

```bash
python -m pip install -r requirements.txt
read -s "KAKAO_REST_API_KEY?Kakao REST API key: "; export KAKAO_REST_API_KEY; echo
read -s "KAKAO_CLIENT_SECRET?Client Secret (Enter if disabled): "; export KAKAO_CLIENT_SECRET; echo
python get_tokens.py
```

브라우저에서 [http://127.0.0.1:5000](http://127.0.0.1:5000)을 열고, **토큰을 받을 가족 본인의 카카오 계정**으로 로그인해 메시지 전송에 동의합니다. 발급 완료 화면에 나온 refresh token을 복사해 해당 `KAKAO_REFRESH_TOKEN_*` Repository secret에 저장하세요. 다음 구성원은 브라우저에서 로그아웃하거나 시크릿 창을 열어 그 사람의 계정으로 같은 절차를 반복합니다. 모두 끝나면 터미널에서 `Ctrl+C`로 서버를 종료하고 토큰 페이지를 닫으세요. 토큰 값을 터미널, 채팅, 코드, 저장소에 붙여 넣지 마세요.

### Refresh token 갱신

Kakao 응답에 새 `refresh_token`이 포함되면 Actions 로그에 계정별 갱신 경고가 남고, 본인 계정 발송이 가능할 경우 본인 나와의 채팅에도 기술 안내가 전달됩니다. 만료되거나 무효가 된 토큰(`KOE322`)은 갱신할 수 없으므로 위 도구를 실행해 해당 가족 계정으로 새 토큰을 발급하세요. **Settings → Secrets and variables → Actions**에서 대응하는 `KAKAO_REFRESH_TOKEN_*` Secret을 새 값으로 교체합니다. 값은 로그나 안내 메시지에 표시되지 않습니다.

## 실행 및 확인

GitHub 저장소의 **Actions → Daily Proverb → Run workflow**에서 수동 실행할 수 있습니다. 실행 로그에는 생성된 문구와 글자 수가 표시되므로 민감한 토큰을 로그에 출력하지 않고 결과를 확인할 수 있습니다.

## 로컬 실행

Python 3.10 이상에서 의존성을 설치하고 Secrets에 해당하는 환경 변수를 설정한 뒤 실행하세요. 예를 들어 본인 계정만 실행할 때:

```bash
python -m pip install -r requirements.txt
export GEMINI_API_KEY="..."
export KAKAO_REST_API_KEY="..."
export KAKAO_REFRESH_TOKEN_ME="..."
export GITHUB_REPOSITORY="owner/repository"
python main.py
```
