# 로케이션핏 — 대화형 AI 입지 추천

> AI 구성부터 파악하려면 [AI 에이전트 중심 프로젝트 아키텍처](docs/ai-agent-architecture.md)를 읽어주세요. 핵심 에이전트 3개, OpenAI Agents SDK, function tool과 결정론적 서비스의 연결을 현재 코드 기준으로 정리했습니다.

사용자가 지정한 조건과 상권 구조의 적합도를 가중 거리로 계산하고, 선택 업종의 신뢰도 보정 과거 성과를 결합해 후보 상권을 추천한다.

예비 창업자는 자연어로 업종·지역·고객·운영 맥락을 설명할 수 있다. 상담 에이전트는 필요한 질문만 최대 4회 진행한 뒤 현재 데이터에서 시장 범위와 제약 충돌을 탐색하고, 조건 충실형·성장 기회형·안정성 우선형 가설을 비교한다. 사용자가 전략과 조건을 명시적으로 확인하면 결정론적 추천 엔진을 실행하고, 상위 3개 상권을 동일 조건 전체 후보 중앙값과 비교한 수치 보고서를 제공한다. 경쟁은 내부 점수가 아니라 최신 동종업종 점포 수와 1㎢당 점포 밀도로 설명한다. AI는 점수와 매출을 생성하거나 재계산하지 않는다.

## 심사위원용 1분 실행

필수 준비물은 **Docker Desktop** 하나다. 저장소 루트에서 다음 명령 하나를 실행한다.

```bash
docker compose up --build
```

첫 실행에는 이미지와 의존성을 내려받아 몇 분이 걸릴 수 있다. PostgreSQL 시작, DB 마이그레이션,
검수된 금융지원 상품 37개 적재, 백엔드 준비 확인 후 프런트엔드 시작까지 자동으로 진행된다.
`bootstrap` 컨테이너가 종료 코드 0으로 끝나는 것은 정상이다.

실행 확인 주소:

- **바로 보는 완성 데모:** `http://localhost:5173/?demo=hongdae-cafe`
- 웹 시작 화면: `http://localhost:5173`
- API 준비 상태: `http://localhost:8000/api/v1/health/ready`
- API 문서: `http://localhost:8000/docs`

완성 데모는 OpenAI 키 없이도 홍대 커피 매장 조건으로 결정론적 추천·비교·자금계획 화면을
구성한다. 자연어 AI 상담과 웹 리서치까지 확인할 때만 `OPENAI_API_KEY` 하나를 추가한다.

PowerShell:

```powershell
$env:OPENAI_API_KEY="<OpenAI API 키>"
docker compose up --build
```

macOS/Linux:

```bash
OPENAI_API_KEY="<OpenAI API 키>" docker compose up --build
```

AI 상담 예시 입력:

> 마포구에서 20대 주말 수요를 겨냥한 커피·음료 매장을 열고 싶어요. 총예산은 1억 5천만원이고,
> 월 환산 임대료 500만원 이하의 1층 66㎡ 매장을 찾고 있어요.

종료는 실행 터미널에서 `Ctrl+C`를 누른 뒤 `docker compose down`을 실행한다. 이 Compose 구성은
로컬 심사용이므로 접속 코드 입력을 생략한다. 인터넷 공개용 배포에서는 아래 운영 보안 설정을
사용해야 한다.

## 웹서비스 구조

웹서비스는 `frontend/`와 `backend/`를 명시적으로 분리한다.

- `frontend/`: React, Vite, TypeScript 기반 대화·맥락/가정·전략 비교·결과 목록·지도·상권 비교 보고서
- `backend/`: FastAPI, 추천 엔진, 서비스용 Parquet 아티팩트와 API 테스트
- `infra/`: 프런트 정적 호스팅과 백엔드 컨테이너의 배포 계약

### Docker 없이 직접 개발

직접 개발 서버를 띄우는 경우에는 Python 3.12, Node.js 22와 PostgreSQL이 필요하다. 먼저
`.env.example`을 `.env`로 복사하고 다음 순서로 실행한다.

```bash
# 터미널 1: API
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
pip install --require-hashes -r requirements-dev.lock
docker compose up -d db
python scripts/bootstrap_demo.py
uvicorn backend.app.main:app --reload

# 터미널 2: 웹
cd frontend
npm ci
npm run dev
```

기본 주소는 웹 `http://localhost:5173`, API 문서 `http://localhost:8000/docs`다.

로컬 개발에서 AI 상담과 선택 상권·업소 웹 리서치를 사용하려면 `.env`에 `OPENAI_API_KEY`를
설정한다. 기본 모델은 `gpt-5.4-mini`이며 `OPENAI_MODEL`로 변경할 수 있다. API 키가 없거나
OpenAI API가 일시적으로 실패하면 기존 추천 데이터와 API는 정상 동작하지만 AI 상담·웹 리서치는
재시도 오류를 반환한다. 인터넷 공개용 운영 데모에서는 별도로 `AI_ACCESS_CODE`와
`AI_SESSION_SECRET`을 설정한다.

운영 데모는 접근 코드로 발급한 서명형 HttpOnly 세션이 있어야 전체 추천·분석 API를 호출할 수
있다. 상태 확인과 세션 발급 API만 인증 전에 열어 두며, 한 번 인증하면 세션 만료 전까지 화면을
자유롭게 탐색할 수 있다. 화면 하단 footer의 `접속 종료`를 누르면 세션 쿠키를 지우고 비밀번호 화면으로
돌아간다. 세 AI 엔드포인트는 PostgreSQL 공용 요청 원장으로 다중 워커에서도
분당 요청, UTC 일일 요청·비용 예약액, 동시 실행 수를 일관되게 제한한다. 운영 환경에서는 이
보호 기능을 끌 수 없으며 HTTPS와 명시적인 `CORS_ORIGINS`를 사용해야 한다. 비용 예약액은 앱 내부 차단용 추정치이므로 OpenAI 프로젝트의
사용량·예산 알림도 함께 확인한다.

대화와 추천 상태는 브라우저 탭의 `sessionStorage`에만 저장된다. 서버는 대화 원문을 저장하지 않고 Agents SDK 추적과 OpenAI 응답 저장을 비활성화한다.

대화창은 추천 상담과 별도로 결정론적 상권 통계 조회를 지원한다. 오른쪽 결과 영역은 `일반조회`, `창업맥락/전략가설`, `입지분석`의 세 페이지로 나뉘며 새 분석 종류에 따라 해당 페이지로 자동 전환된다. 이 세 페이지와 입지분석 안의 `상권분석`은 하나의 입지 AI와 대화 기록을 이어서 사용한다. `입지분석` 안은 다시 `상권분석`, `상권내 점포 분석`, `자금계획`으로 분리되어 지도·추천·보고서, 상권 내부 업소, 임대매물·정책자금 화면을 각각 독립적으로 보여준다. `상권내 점포 분석`과 `자금계획`은 별도 전용 AI와 독립 대화 기록을 사용하며, 서버에서 현재 상권·업종·임대 후보에 묶인 읽기·계산 도구를 직접 호출한다. 도구 결과와 기준일·가정·경고는 대화 아래 근거 카드로 함께 표시되며 후보 저장값은 자동 변경하지 않는다. 상권·업종·자치구·행정동을 최근 매출, 폐업률, 개업률, 매출 성장률, 점포 수·밀도, 유동·상주·직장인구 기준으로 Top 1~50 오름차순/내림차순 조회할 수 있다. 결과에는 필터 적용 후 전체 조회 대상의 평균·중앙값·모집단 표준편차와 각 순위 값의 평균/중앙값 대비 차이·표준편차 거리도 포함한다. 상권·자치구 순위는 추천지도와 같은 메인 지도 영역에 조회 경계를 표시하며, 결과 행이나 경계를 선택하면 현재 조회 지표의 값·순위·평균/중앙값 대비 차이·표준편차 거리를 확인할 수 있다. 업종·행정동 순위는 목록으로만 표시한다. 예: `매출 높은 상권 5곳`, `가장 매출 높은 업종 10개`, `강남구 역삼1동에서 폐업률 높은 업종 5개`. 동 단위는 원천 데이터의 상권별 대표 행정동 기준이며 법정동 경계 집계가 아니다.

### 추천 상권 내 영업 점포 분석

추천 결과에서 상권을 선택한 뒤 `이 상권 점포 분석`을 누르면 소상공인시장진흥공단 상가(상권)정보 API를 실시간 조회한다. 실제 상권 Polygon/MultiPolygon 경계 안의 업소만 표시하며, 추천 업종과의 명시적 교차표에 따라 직접 경쟁점·보완 업종·생활시설·기타 업소로 구분한다. 지도는 점포를 군집화하고 관계 필터와 상호·업종·주소 검색을 제공한다.

이 데이터의 “상가업소”는 현재 영업 중인 사업체이며 임대매물이 아니다. 보증금·월세·권리금·임대면적·공실 여부를 제공하지 않으므로 화면과 API 응답에도 이 제한을 고정 표시한다.

서버 환경에 아래 값을 설정한다.

```bash
DATA_GO_KR_SERVICE_KEY=<공공데이터포털 인증키>
SBIZ_STORE_API_BASE_URL=https://apis.data.go.kr/B553077/api/open/sdsc2
STORE_CACHE_TTL_SECONDS=86400
STORE_STALE_TTL_SECONDS=604800
STORE_API_TIMEOUT_SECONDS=15
STORE_RATE_LIMIT_PER_MINUTE=5
```

- `GET /api/v1/areas/{area_code}/stores?industry_code={code}`: 선택 상권 업소와 관계별 요약 조회
- `POST /api/v1/market-geographies`: 단순조회 상권·자치구 결과의 지도 경계 조회(최대 50개)
- `POST /api/v1/agent/workspace-turns`: 점포분석·자금계획 페이지별 독립 AI 대화
- 원본 조회는 24시간 메모리 캐시하며 외부 API 장애 시 프로세스에 남은 7일 이내 결과를 경고와 함께 사용한다.
- API 키가 없어도 기존 상권 추천은 정상 동작하고 점포 상세 조회만 503 오류를 반환한다.

상권 상세 화면의 검색 버튼 또는 점포분석 AI 대화에서 최신·외부 조사를 명시적으로 요청한 경우에만 OpenAI 웹 검색을 실행한다. 결과는 검색시각과 출처 링크를 포함하며 서버 캐시나 벡터 데이터베이스에는 적재하지 않는다. 웹 검색에는 `OPENAI_API_KEY`가 필요하고 제한 시간은 `WEB_RESEARCH_TIMEOUT_SECONDS`, 웹 검색을 포함할 수 있는 워크스페이스 전체 제한 시간은 `WORKSPACE_AGENT_TIMEOUT_SECONDS`로 조정한다.

### 임대매물·금융지원 1차 계획

2단계 상권 점포 화면에서 주변 경쟁점·보완업종을 검토한 뒤 `임대매물 추가`로 사용자가 직접 찾은 실제 매물을 후보함에 넣는다. 한 상권에 여러 후보를 저장하고 보증금, 월 고정 임차비, 권리금, 첫해 임차 현금 필요액을 비교한 뒤 한 건을 3단계 금융계획 대상으로 선택한다. 후보는 브라우저 탭의 `sessionStorage`에만 저장되며 추천 조건을 새로 확정하거나 전체 초기화하면 함께 제거된다.

매물명, 주소, 보증금, 월세, 관리비, 권리금, 임대면적, 층은 사용자가 직접 확인해 입력한다. 빈 관리비·권리금은 `미확인`으로 유지하고 사용자가 0을 입력한 경우에만 비용 없음으로 확정한다. 미확인 비용이 있으면 비교 합계와 금융계획 생성을 차단한다.

자금계획은 `보증금 + 권리금 + 12개월치 월세·관리비 + 인테리어·설비·초도물품·운영자금·기타 비용`으로 첫해 현금 필요액을 계산하고 자기자금과의 차이를 보여준다. 부가세, 공과금, 중개보수는 포함하지 않는다. 금융지원 후보는 AI가 결정하지 않으며 PostgreSQL 카탈로그의 자격조건에 입력한 소상공인 여부, 사업상태·업력, 금융취약 요건, 미소금융 성실상환 이력, 융자제외 업종 여부를 결정론적으로 적용한다. 미입력 조건은 탈락시키지 않고 추가 확인사항으로 돌려준다. 현재 검수 카탈로그 기준일은 2026-07-29이며, 결과는 승인 가능성이 아니라 `기본조건 부합`, `추가 확인 필요`, `입력조건상 비대상`의 1차 후보다.

자금계획 AI는 현재 후보 재계산, 후보 간 비교, 정책지원 상세 조회와 일회성 가정 계산 도구를 직접 호출한다. “인테리어비를 2천만원으로 보면?” 같은 가정은 응답에 변경값을 표시하지만 브라우저에 저장된 후보와 자금계획을 수정하지 않는다.

- `POST /api/v1/finance/plans`: 확인된 매물의 첫해 필요자금과 DB 금융지원 상품 후보 계산
- 상품 범위: KB국민은행 5종, 소상공인 정책자금 11종, 서울시 중소기업육성자금 16종, 미소금융 4종, 보증 연계 사업 1종

### 금융지원 상품 카탈로그 DB

은행대출·정책자금·지원사업·보증상품의 현재 정보를 담기 위한 PostgreSQL 스키마가
준비되어 있다. 초기 37개 검수 데이터와 기업마당 API 수집 결과를 preview한 뒤
승인 반영하는 적재 도구를 제공한다. `POST /api/v1/finance/plans`는 현재 DB의
`active`, `upcoming`, `unknown` 상품을 읽어 구조화된 자격조건을 결정론적으로
비교하고, 프런트엔드는 상품 유형·혜택·확인사항·공식 출처를 카드로 표시한다.

심사용 Compose에서는 `bootstrap` 서비스가 마이그레이션과 초기 검수 카탈로그 적재를 자동으로
수행한다.

```bash
docker compose up --build
```

호스트에서 백엔드를 직접 실행할 때는 `.env.example`의 `DATABASE_URL`을 사용하고 부트스트랩
스크립트를 한 번 실행한다. 기존 상품이 있으면 덮어쓰지 않는다.

```bash
docker compose up -d db
python scripts/bootstrap_demo.py
```

- 추천 모델과 서울 상권 데이터는 기존 Parquet 아티팩트를 계속 사용한다.
- PostgreSQL은 금융지원 카탈로그와 AI 요청 제한용 최소 원장만 담당한다. 대화 원문은 저장하지 않는다.
- 자격조건 그룹 간에는 OR, 한 그룹 안의 조건 간에는 AND 의미를 갖는다.
- 상품 조건 변경 시 과거 리비전을 만들지 않고 현재 행과 확인시각을 갱신한다.

초기 검수 카탈로그에는 2026-07-29 공식 안내 기준으로 KB국민은행 5종, 소상공인
정책자금 11종, 서울시 중소기업육성자금 16종, 미소금융 4종,
신용보증재단중앙회 보증 연계 사업 1종이 정의되어 있다. 금액·금리 등 공식 원문에서 구조적으로 확정하지 못한 값은
0으로 추정하지 않고 `null`로 유지한다. 서울시 안심통장은 별도 시행공고의 현재
상태를 추가 확인해야 하므로 `unknown` 상태다.

검수 데이터와 기업마당 API 결과는 DB에 바로 쓰지 않는다. 먼저 preview에서 원본,
검증 결과와 DB diff를 확인한 뒤 해당 실행 디렉터리를 명시해 반영한다.

```bash
# 검수 YAML만 비교
.venv/bin/python scripts/manage_financial_catalog.py preview --source curated

# 기업마당 금융·서울·소상공인 공고 포함(BIZINFO_API_KEY 필요)
.venv/bin/python scripts/manage_financial_catalog.py preview --source all

# 출력된 경로의 diff.json과 validation.json 검토 후 반영
.venv/bin/python scripts/manage_financial_catalog.py apply \
  --run-dir outputs/financial_catalog/<UTC실행시각>

# 현재 DB 품질 확인
.venv/bin/python scripts/manage_financial_catalog.py validate
```

- 기업마당 API 키는 `BIZINFO_API_KEY`에만 저장하며 원본·manifest·로그에는 기록하지 않는다.
- 기업마당은 금융 분야이면서 서울 적용 및 소상공인·개인사업자·창업자 대상인 공고만 포함한다.
- API 본문의 금액·금리 문장은 자동 수치화하지 않고 검수 YAML로 보강한 값만 사용한다.
- 같은 공고가 여러 세부자금의 출처이면 `source_aliases.yaml`로 명시적으로 연결한다.
- 권장 확인 주기는 기업마당 매일, KB·정책자금·보증상품 주 1회다. 스케줄러는 별도다.

서비스 아티팩트를 다시 만들려면 저장소 루트에서 아래 명령을 실행한다.

```bash
.venv/bin/python backend/pipelines/scripts/build_service_artifacts.py
```

- 기존 API 기본값 `balanced`: 상권 구조 적합도 60%, 신뢰도 보정 과거 성과 40%
- `condition_fit`: 조건 적합 75%, 성과 근거 25%
- `growth`: 조건 적합 45%, 성장 중심 성과 근거 55%
- `stability`: 조건 적합 45%, 안정성 중심 성과 근거 55%

최종점수의 전략별 비중은 고정되어 있다. 선택적으로 `performance_group_weights`를 보내면 업종 성과 내부의 5개 그룹 비중만 바뀌며, 서버가 합계 1로 정규화한다. 5개 키는 모두 필요하다.

```json
{
  "industry_code": "CS100001",
  "strategy": "balanced",
  "performance_group_weights": {
    "scale_productivity": 20,
    "growth": 40,
    "stability": 20,
    "competition": 5,
    "closure_risk": 15
  }
}
```

실제 적용값과 출처는 응답 `diagnostics.performance_group_weights`, `diagnostics.performance_weights_source`에 있으며, 각 후보의 `performance_breakdown`은 그룹 점수·요청 비중·결측 재정규화 후 실효 비중·원시 업종 성과점수 기여도를 제공한다.

상담 중 서울 열린데이터나 서울시 상권분석서비스를 실시간 호출하지 않으며 배포 아티팩트만 읽는다. 추천 엔진은 데이터베이스를 사용하지 않는다. 추천 지도는 서울시 `상권분석서비스(영역-상권)` SHP(EPSG:5181)를 WGS84로 변환한 실제 Polygon/MultiPolygon 경계를 표시한다. 월 환산임대료 한도와 임대면적·층 구분을 모두 입력하면 기존 종합점수 80%와 임대예산 적합도 20%를 결합해 재정렬한다. 총 창업예산만 입력하거나 예산을 입력하지 않으면 기존 순위와 점수를 유지한다.

서비스 아티팩트를 다시 만들 때는 서울 열린데이터광장 OA-15560의 `서울시 상권분석서비스(영역-상권).zip`을 풀어 SHP 구성 파일을 `data/raw/area/`에 둔다. 빌드 결과인 `area_boundaries.parquet`에는 1,650개 상권코드별 GeoJSON 경계가 저장된다. 자치구 지도는 [국가데이터처 JUSO 시군구 경계의 2015 GeoJSON 변환본](https://github.com/southkorea/seoul-maps/tree/master/juso/2015/json)을 사용하며, `data/raw/district/`의 SHP 또는 GeoJSON에서 서울 25개 자치구와 도형 유효성을 검증해 `district_boundaries.parquet`으로 만든다.

### 서울시 상권분석서비스 임대시세 수동 갱신

서울시 상권분석서비스에서 서울신용보증재단 보증 고객 통계 기반의 행정동별 환산임대료를 분기 단위로 내려받는다. 공식 서비스가 제공하는 `전체 층 평균`, `1층`, `1층 외`의 3.3㎡당 월 환산임대료를 서울 상권유형·상권명으로 직접 결합한다.

```bash
PYTHONPATH=. .venv/bin/python scripts/refresh_seoul_commercial_rent.py
```

갱신 결과는 `backend/artifacts/current/commercial_rent_observations.parquet`이며 `manifest.json`에 행 수·체크섬·기준 분기가 추가된다. 원본 응답은 `data/raw/seoul_commercial_rent/<UTC시각>/`에 원자적으로 저장된다. 특정 분기는 `--year 2026 --quarter 1`, 저장된 원본 재가공은 `--from-raw <디렉터리>`로 지정한다. 별도 인증키나 스케줄러는 없으며 분기 발표 후 수동 실행한다.

표시되는 임대료는 해당 상권이 속한 행정동의 임대시세를 임대면적(전용+공용)에 적용한 월 환산임대료 추정치다. 관리비와 부가가치세는 제외한다. 선택한 1층/1층 외 값이 없으면 같은 분기의 전체 층 평균을 사용하고, 행정동 값 전체가 없으면 같은 분기의 자치구 값을 사용해 화면에 대체 사실을 표시한다. 결과 화면에서 보증금을 입력하면 서울시 환산 산식의 연 12%를 적용해 `max(0, 환산 월 임대료 - 보증금 × 12% ÷ 12)`로 현금 월세와 첫해 현금 지출을 계산하고, 반환 가능한 보증금은 별도로 표시한다.

## 데이터 기간

- 업종 과거 성과: 2021Q1~2025Q4(20개 분기)
- 현재 상권 구조 프로필: 2024Q1~2025Q4(8개 분기)
- 최근성 신뢰도: `0.7 ** quarter_age`(`03_build_area_industry_evidence.ipynb`에서 적용, 4분기 이상 미관측 조합 제외)
- 향후 외부 검증: 2026Q1(필수 데이터 전체 확보 전까지 비활성)

기간은 [config/datasets.yaml](config/datasets.yaml)에서 변경한다. 2024년 전후 공간 단위 호환성은 병합 전 `check_historical_compatibility.py`로 반드시 검토한다.

## 환경 설정

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --require-hashes -r requirements-dev.lock
cp .env.example .env
# .env에 SEOUL_API_KEY 입력
```

`.env`와 API 키는 Git에 포함하지 않으며, API 키는 로그·CSV·메타데이터에 저장하지 않는다. [서울시 공식 Open API 가이드](https://data.seoul.go.kr/together/guide/useGuide.do)는 현재 인증키를 URL 경로에 넣는 `http://openapi.seoul.go.kr:8088` 호출을 안내한다. 이 키는 다른 서비스에서 재사용하지 않는 수집 전용 키로 발급하고, 공용 Wi-Fi가 아닌 신뢰할 수 있는 제한된 수집 환경에서만 사용한다.

## 원본 데이터 수집

`data/raw/sales/`의 2021~2025 연도별 추정매출 CSV는 기본적으로 재사용하며 변경하지 않는다. `--all`은 sales를 검증 대상으로만 표시하고 API 다운로드를 건너뛴다.

```bash
.venv/bin/python scripts/download_seoul_data.py \
  --dataset stores --quarters 20211 --debug-api \
  --allow-insecure-seoul-http

.venv/bin/python scripts/download_seoul_data.py \
  --all --skip-sales \
  --allow-insecure-seoul-http
```

`--allow-insecure-seoul-http`는 제공자 제약으로 남은 평문 HTTP 위험을 인지하고 이번 수집 실행에만 허용하는 플래그다. 플래그가 없으면 네트워크 요청 전에 중단한다. 클라이언트는 공식 호스트·포트만 허용하고 리다이렉트를 따르지 않는다. `--debug-api`는 첫 5행 응답만 진단하고 파일을 저장하지 않는다. 전체 수집이 중간에 실패하면 같은 `--all --skip-sales` 명령을 다시 실행하면 이미 저장된 파일을 건너뛰고 이어받는다.

추정매출 API 재수집은 아래처럼 데이터셋과 덮어쓰기 의도를 둘 다 명시해야 한다. 기존 연도별 파일은 수정하지 않고 `sales_YYYYQ.csv`를 별도 생성한다.

```bash
.venv/bin/python scripts/download_seoul_data.py \
  --dataset sales --overwrite --allow-insecure-seoul-http
```

분기 파일은 `data/raw/<dataset>/<prefix>_20211.csv`, 비분기 영역 데이터는 `data/raw/area/area.csv`로 저장된다. 각 CSV 옆에 인증 정보가 없는 `.meta.json`이 생성된다.

`--debug-api`는 HTTP 상태, Content-Type, 본문 길이·앞 500자, redirect, JSON 최상위 키, total count와 첫 페이지 행 수를 출력한다. URL·본문·예외의 API 키는 `***MASKED***`로 치환되며, 진단 모드에서는 raw 파일을 저장하지 않는다.

## 검증과 interim 생성

```bash
.venv/bin/python scripts/check_raw_data.py
.venv/bin/python scripts/check_historical_compatibility.py
```

검증 결과는 `outputs/tables/`의 인벤토리·스키마·중복·분기 커버리지·코드 교집합·연도별 분포 보고서로 저장된다. 필수 데이터가 없으면 `check_raw_data.py`는 보고서를 남긴 후 종료 코드 1을 반환한다.

공식 노트북 파이프라인은 다음 순서다.

1. `notebooks/00_data_inventory.ipynb`
2. `notebooks/01_ingest_clean.ipynb`
3. `notebooks/02_build_area_profile.ipynb`
4. `notebooks/03_build_area_industry_evidence.ipynb`
5. `notebooks/04_build_recommender.ipynb`

저장소 루트에서 아래 명령을 실행하면 다섯 노트북을 순차 실행하고 각 결과를 `notebooks/*.executed.ipynb`로 저장한다. 앞 단계가 실패하면 셸이 즉시 종료되므로 불완전한 산출물을 다음 단계가 소비하지 않는다.

```bash
set -e
notebooks=(
  notebooks/00_data_inventory.ipynb
  notebooks/01_ingest_clean.ipynb
  notebooks/02_build_area_profile.ipynb
  notebooks/03_build_area_industry_evidence.ipynb
  notebooks/04_build_recommender.ipynb
)

for notebook in "${notebooks[@]}"; do
  output="$(basename "${notebook%.ipynb}").executed.ipynb"
  .venv/bin/jupyter nbconvert --to notebook --execute "$notebook" --output "$output"
done
```

`02_build_area_profile.ipynb`는 최근 8개 분기의 상권 구조 프로필을, `03_build_area_industry_evidence.ipynb`는 20개 분기의 상권×업종 관측 성과와 신뢰도를 생성한다. `04_build_recommender.ipynb`는 추천 인덱스를 만들고 예시 시나리오의 결정성·점수 범위·가중치 민감도·k 안정성을 검증한 뒤 서비스 입력 및 검증 CSV를 내보낸다. 2026Q1 데이터가 모두 확보되기 전에는 별도의 시간 외부 검증 단계를 실행하지 않는다.

주요 최종 산출물은 다음과 같다.

- `data/processed/area_profile.parquet`
- `data/processed/area_industry_evidence.parquet`
- `data/processed/area_recommendation_index.parquet`
- `outputs/tables/area_industry_evidence_validation.csv`
- `outputs/tables/recommender_validation.csv`
- `outputs/tables/recommender_sample_results.csv`
- `outputs/tables/recommender_weight_sensitivity.csv`
- `outputs/tables/recommender_k_stability.csv`

`01_ingest_clean.ipynb`는 원본 한글/API 키를 아래 문자열 컬럼으로 표준화하고 `data/interim/<dataset>.parquet`를 생성한다.

- `quarter` ← `기준_년분기_코드` / `STDR_YYQU_CD`
- `area_code` ← `상권_코드` / `TRDAR_CD`
- `area_name` ← `상권_코드_명` / `TRDAR_CD_NM`
- `industry_code` ← `서비스_업종_코드` / `SVC_INDUTY_CD`
- `industry_name` ← `서비스_업종_코드_명` / `SVC_INDUTY_CD_NM`

완전 동일 행만 제거하며, 상권×업종×분기 또는 상권×분기 키 중복은 자동 삭제하지 않고 `data/interim/ingest_diagnostics.csv`에 원인을 보고한다.

기존 `data/interim/sales.parquet`이 있으면 현재 raw 적재 결과와 행 수·키·기간을 검증한 뒤 파일을 보존한다.

## 2026-07-16 수집·검증 결과

| dataset | rows | quarter range | quarter count | status |
|---|---:|---|---:|---|
| area | 1,650 | 비분기 | - | OK |
| sales | 439,141 | 20211~20254 | 20 | 기존 파일 재사용 |
| stores | 1,528,872 | 20211~20254 | 20 | OK |
| floating_population | 32,984 | 20211~20254 | 20 | OK |
| resident_population | 32,642 | 20211~20254 | 20 | OK |
| worker_population | 32,745 | 20211~20254 | 20 | OK |
| facilities | 31,560 | 20211~20254 | 20 | OK |
| apartments | 29,327 | 20211~20254 | 20 | OK |
| commercial_change | 33,000 | 20211~20254 | 20 | OK |

raw 및 interim 모두 완전 중복과 설정 grain 키 중복이 0이며, 모든 데이터셋의 상권코드는 area master와 조인된다. 2023→2024 상권코드 유지율은 데이터셋별 99.68~100%이고 주요 수치형 변수의 중앙값 변화는 0~-2.74%로 동시 급변 경고가 없다. 다만 추정매출 업종 `CS200036`(고시원)은 마지막 관측 분기가 20233이므로 장기 업종 성과 계산에서 관측 분기 수와 신뢰도를 반영해야 한다.

상권 구조 프로필은 2024Q1~2025Q4 최근 8개 분기, 업종 과거 성과는 2021Q1~2025Q4 전체 20개 분기를 사용한다.

## 품질 검사와 의존성 잠금

```bash
.venv/bin/ruff check backend src scripts tests
.venv/bin/mypy
.venv/bin/pip-audit --disable-pip --requirement backend/requirements.lock
.venv/bin/pip-audit --disable-pip --requirement requirements-dev.lock
.venv/bin/python -m pytest -q

cd frontend
npm ci
npm run lint
npm run typecheck
npm test
npm run build
```

백엔드 운영 의존성의 허용 범위는 `backend/requirements.txt`, 데이터 분석·로컬 실행 의존성은 `requirements.txt`, 개발 도구는 `requirements-dev.txt`에 둔다. Docker와 CI는 Linux/Python 3.12에서 해석하고 배포 파일 해시까지 기록한 `backend/requirements.lock`의 동일한 운영 버전을 사용한다. CI와 로컬 개발은 이 운영 잠금을 포함하는 `requirements-dev.lock`을 추가로 사용한다. 의존성을 의도적으로 갱신할 때만 Python 3.12 환경에서 아래 순서로 잠금 파일을 다시 만든다.

```bash
python -m piptools compile --upgrade --generate-hashes --strip-extras \
  --output-file=backend/requirements.lock backend/requirements.txt
python -m piptools compile --upgrade --generate-hashes --allow-unsafe --strip-extras \
  --output-file=requirements-dev.lock requirements-dev.txt
```

mypy는 `src`와 `backend/app` 전체를 검사한다. GitHub Actions는 push와 pull request마다 Python lint/type/test 및 PostgreSQL 마이그레이션·통합 테스트, 프런트 lint/type/test/build를 같은 명령으로 실행한다.

노트북 실행 검증이 필요하면 별도로 실행한다.

```bash
.venv/bin/jupyter nbconvert --to notebook --execute notebooks/00_data_inventory.ipynb \
  --output 00_data_inventory.executed.ipynb
```

모든 `api_service_name`은 서울 열린데이터광장의 각 OA 데이터셋 OpenAPI 명세에서 확인한 값이다. 분기 경로 필터를 공식으로 제공하지 않는 서비스는 전체 페이지를 수집한 뒤 `STDR_YYQU_CD`로 로컬 필터링·분할한다.
