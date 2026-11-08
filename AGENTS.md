# morning-proverb AI Context & System State

> 이 파일은 AI 코딩 어시스턴트가 `morning-proverb` 프로젝트의 현 상태, 아키텍처, 스케줄링 방식, 카카오톡 인증 구조를 즉시 파악하도록 돕는 컨텍스트 문서입니다.

---

## 1. 프로젝트 개요 & 목적
- **목적**: 
  - 매일 아침 서울 날씨(`wttr.in`)와 날짜 감성을 기반으로 Google Gemini API(`gemini-3.8-flash`)를 통해 200자 이내의 맞춤형 성경 잠언 및 묵상 메시지를 생성.
  - 가족(본인, 배우자, 딸, 어머니, 장인어른, 장모님)에게 카카오톡 나와의 채팅 메시지로 발송.
  - 발송된 잠언 히스토리를 `docs/proverbs.json`에 영구 보관하고 GitHub Pages 웹사이트로 자동 게시.
- **실행 시간**: **매일 아침 07:00 정각 (한국 표준시 KST)**

---

## 2. 아키텍처 & 스케줄링 구조 (★핵심)

```mermaid
flowchart TD
    subgraph 이전_구조["[이전 구조] GitHub Actions 내장 Cron (문제점)"]
        A1["GitHub Actions schedule cron<br>(02:27 KST)"] -->|무료 큐 지연으로 15분~1시간 지연| A2["메시지 늦게 도착"]
    end

    subgraph 현재_구조["[현재 구조] Google Cloud Scheduler 정시 트리거 (완전 해결)"]
        B1["Google Cloud Scheduler (0 7 * * *)"] -->|매일 07:00:00 칼같이 호출 (오차 0초)| B2["GitHub Actions workflow_dispatch API"]
        B2 --> B3["wttr.in 날씨 조회 + Gemini 3.8 Flash 잠언 생성"]
        B3 --> B4["가족 전원(all) 카카오톡 발송"]
        B4 --> B5["docs/proverbs.json 히스토리 커밋 및 Pages 배포"]
    end
```

- **트리거 인프라**: **Google Cloud Scheduler**
  - 작업 이름: `morning-proverb-daily`
  - 리전: `asia-northeast3` (서울)
  - 빈도: `0 7 * * *` (KST 매일 아침 07:00)
  - 호출 대상: `POST https://api.github.com/repos/jinugkim/morning-proverb/actions/workflows/daily-proverb.yml/dispatches`
- **정시성**: GitHub Actions 내장 크론 큐의 지연을 우회하여 **매일 아침 7시 00분에 1~2분 내로 정확히 발송**됨.

---

## 3. 카카오톡 인증 및 courier와의 관계
- **독립형 자체 발송**: 중앙 라우터(`courier`)를 거치지 않고 `morning-proverb` 내부의 `main.py`가 카카오 OAuth 토큰 관리 및 발송을 직접 수행함.
- **다중 수신자 발송**:
  - `KAKAO_REFRESH_TOKEN_ME` (본인)
  - `KAKAO_REFRESH_TOKEN_WIFE` (배우자)
  - `KAKAO_REFRESH_TOKEN_DAUGHTER` (딸)
  - `KAKAO_REFRESH_TOKEN_MOTHER` (어머니)
  - `KAKAO_REFRESH_TOKEN_FATHER_IN_LAW` (장인어른)
  - `KAKAO_REFRESH_TOKEN_MOTHER_IN_LAW` (장모님)
- **외부 API 호출 대응**: `workflow_dispatch` 호출 시 파라미터를 넘기지 않더라도 `recipient`가 `'all'`로 자동 폴백되도록 워크플로에 방어 로직 적용 완료.

---

## 4. 핵심 파일 및 역할
- `.github/workflows/daily-proverb.yml`: Cloud Scheduler 또는 수동 실행을 받는 GitHub Actions 워크플로
- `.github/workflows/pages.yml`: `docs/proverbs.json` 변경 시 정적 사이트 배포
- `main.py`: 날씨 조회, Gemini 잠언 생성, 카카오톡 발송, JSON 히스토리 갱신 전체 파이프라인
- `docs/proverbs.json`: 역대 전송된 잠언 목록 데이터
- `get_tokens.py`: 로컬에서 카카오 토큰 발급 및 수동 갱신용 Flask 서버

---

## 5. 저장소 GitHub Secrets 레퍼런스
- `GEMINI_API_KEY`: Google Gemini API 키 (`gemini-3.8-flash` 구동용)
- `KAKAO_REST_API_KEY`: 카카오 Developers REST API 키
- `KAKAO_CLIENT_SECRET`: 카카오 Developers Client Secret (활성화된 경우)
- `KAKAO_REFRESH_TOKEN_*`: 각 가족별 카카오 리프레시 토큰들
