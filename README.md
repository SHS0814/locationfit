# 로케이션핏 — 대화형 AI 입지 추천

## 개요

로케이션핏은 예비 창업자의 업종·지역·고객·예산 조건을 대화로 정리하고, 서울 상권 데이터에
근거해 후보 상권을 추천하는 웹서비스입니다. 조건 충실형·성장 기회형·안정성 우선형 전략을
비교한 뒤 상위 3개 상권과 후보군 중앙값 대비 차이를 제공합니다.

AI는 상담과 도구 선택을 담당하며 점수·매출을 생성하거나 재계산하지 않습니다. 최종 추천,
상권 통계, 임대비용과 금융지원 후보는 서버의 결정론적 서비스가 계산합니다.

---

## 빠른 실행

필수 준비물은 **Docker Desktop**입니다. 저장소 루트에서 명령 하나를 실행합니다.

```bash
docker compose up --build
```

PostgreSQL 시작, DB 마이그레이션, 검수 금융상품 37개 적재, 백엔드 준비 확인과 프런트엔드
시작이 자동으로 진행됩니다. `bootstrap` 컨테이너가 종료 코드 0으로 끝나는 것은 정상입니다.

- 완성 데모: `http://localhost:5173/?demo=hongdae-cafe`
- 웹 시작 화면: `http://localhost:5173`
- API 상태: `http://localhost:8000/api/v1/health/ready`
- API 문서: `http://localhost:8000/docs`

완성 데모와 결정론적 추천은 OpenAI 키 없이 실행됩니다. 자연어 AI 상담과 웹 리서치까지
확인할 때만 `OPENAI_API_KEY`를 설정합니다.

PowerShell:

```powershell
$env:OPENAI_API_KEY="<OpenAI API 키>"
docker compose up --build
```

macOS/Linux:

```bash
OPENAI_API_KEY="<OpenAI API 키>" docker compose up --build
```

AI 상담 예시:

> 마포구에서 20대 주말 수요를 겨냥한 커피·음료 매장을 열고 싶어요. 총예산은 1억 5천만원이고,
> 월 환산 임대료 500만원 이하의 1층 66㎡ 매장을 찾고 있어요.

종료:

```bash
docker compose down
```

---

## 핵심 기능

1. **입지 상담 AI**
   - 자연어 조건 구조화, 시장 범위 탐색, 3가지 전략 가설 비교
   - 사용자 확인 후 결정론적 추천 엔진 실행
2. **상권·점포 분석 AI**
   - 매출·성장률·폐업률·점포 밀도·인구 기준 순위 조회
   - 추천 상권 경계 안의 경쟁점·보완업종·생활시설 분석
3. **자금계획 AI**
   - 보증금·월세·관리비·권리금과 창업비용으로 첫해 필요자금 계산
   - 검수된 금융지원 상품 37개의 자격조건을 결정론적으로 비교

점포 실시간 조회에는 선택적으로 `DATA_GO_KR_SERVICE_KEY`가 필요합니다. 키가 없어도 추천과
완성 데모는 정상 동작합니다.

---

## 서비스 흐름

1. 사용자가 업종과 희망 조건을 입력합니다.
2. 입지 AI가 조건과 가정을 정리하고 전략 3가지를 비교합니다.
3. 사용자가 전략을 확인하면 추천 엔진이 상위 3개 상권을 계산합니다.
4. 선택 상권의 실제 영업 점포와 사용자가 입력한 임대 후보를 검토합니다.
5. 첫해 필요자금과 금융지원 1차 후보를 확인합니다.

대화와 추천 상태는 브라우저 탭의 `sessionStorage`에만 저장합니다. 서버는 대화 원문을 저장하지
않고 Agents SDK 추적과 OpenAI 응답 저장을 비활성화합니다.

---

## 프로젝트 구조

```text
frontend/                 React·Vite·TypeScript 웹 화면
backend/app/              FastAPI, AI 에이전트, 추천·금융 서비스
backend/artifacts/current 서비스용 Parquet 추천 아티팩트
backend/migrations/       PostgreSQL 스키마 마이그레이션
src/                      데이터 전처리·추천 모델 코드
config/                   데이터셋·모델·금융상품 검수 설정
notebooks/                데이터 검증·모델 생성 파이프라인
scripts/                  초기화·수집·검증·카탈로그 관리 도구
tests/, backend/tests/    백엔드·데이터 테스트
compose.yaml              심사용 원클릭 실행 구성
```

---

## 기술 스택

| 영역 | 기술 |
|---|---|
| Frontend | React 19, TypeScript, Vite, Leaflet |
| Backend | FastAPI, Pydantic, OpenAI Agents SDK |
| Data/ML | pandas, scikit-learn, PyArrow, Shapely |
| Database | PostgreSQL 17, SQLAlchemy, Alembic |
| Runtime | Docker Compose, Nginx |

---

## 데이터와 추천 기준

- 업종 과거 성과: 2021Q1~2025Q4, 20개 분기
- 현재 상권 구조 프로필: 2024Q1~2025Q4, 8개 분기
- 공간 범위: 서울시 상권 1,650개 Polygon/MultiPolygon
- 데이터 출처: 서울 열린데이터광장, 소상공인시장진흥공단, 금융기관 공식 안내
- 추천 결과: 조건 적합도와 신뢰도 보정 과거 성과를 전략별 고정 비중으로 결합
- 비교 기준: 동일 조건 전체 후보 중앙값, 최신 동종업종 점포 수와 1㎢당 밀도

추천은 미래 매출이나 사업 성공을 보장하지 않습니다. 상가업소 정보는 현재 영업 사업체이며
임대매물 정보가 아닙니다. 금융지원 결과도 승인 가능성이 아닌 1차 조건 비교입니다.

---

## 데이터 파이프라인

```text
원천 데이터 수집
→ 스키마·중복·분기·상권코드 검증
→ 상권 구조 프로필 생성
→ 상권×업종 성과와 신뢰도 계산
→ 추천 인덱스·지도 경계·검증 결과 생성
→ backend/artifacts/current 배포
```

주요 실행 도구는 `scripts/`에, 공식 분석 순서는 `notebooks/00_...`부터 `04_...`까지 정리되어
있습니다. 서비스 아티팩트는 다음 명령으로 다시 생성할 수 있습니다.

```bash
python backend/pipelines/scripts/build_service_artifacts.py
```

---

## 품질 검사

백엔드와 데이터:

```bash
python -m pip install --require-hashes -r requirements-dev.lock
python -m ruff check backend src scripts tests
python -m mypy
python -m pytest -q
```

프런트엔드:

```bash
cd frontend
npm ci
npm run lint
npm run typecheck
npm test
npm run build
```

운영 API 키와 비밀번호는 Git에 포함하지 않습니다. 로컬 개발 변수 예시는 `.env.example`을
사용하고, 제출 파일은 태그에서 `git archive`로 생성합니다.
