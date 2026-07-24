# KB AI Challenge — 대화형 AI 입지 추천

> 처음 프로젝트를 받았다면 [개발자 온보딩 문서](project/docs/README.md)부터 읽어주세요. 아키텍처, 로컬 실행, 데이터 파이프라인, 추천 로직, API, 프런트엔드, 테스트·배포와 변경 가이드를 코드 기준으로 정리했습니다.

선택 업종의 과거 성과가 우수했던 상권을 참조 집단으로 정의하고, 구조적으로 유사한 후보를 가중 KNN으로 탐색한 뒤 신뢰도 보정 과거 성과를 결합한다.

예비 창업자는 자연어로 업종·지역·고객·운영 맥락을 설명할 수 있다. 상담 에이전트는 필요한 질문만 최대 4회 진행한 뒤 현재 데이터에서 시장 범위와 제약 충돌을 탐색하고, 조건 충실형·성장 기회형·안정성 우선형 가설을 비교한다. 사용자가 전략과 조건을 명시적으로 확인하면 결정론적 추천 엔진을 실행하고, 상위 3개 상권을 동일 조건 전체 후보 중앙값과 비교한 수치 보고서를 제공한다. 경쟁은 내부 점수가 아니라 최신 동종업종 점포 수와 1㎢당 점포 밀도로 설명한다. AI는 점수와 매출을 생성하거나 재계산하지 않는다.

## 웹서비스 구조

웹서비스는 `frontend/`와 `backend/`를 명시적으로 분리한다.

- `frontend/`: React, Vite, TypeScript 기반 대화·맥락/가정·전략 비교·결과 목록·지도·상권 비교 보고서
- `backend/`: FastAPI, 추천 엔진, 서비스용 Parquet 아티팩트와 API 테스트
- `infra/`: 프런트 정적 호스팅과 백엔드 컨테이너의 배포 계약

로컬 실행:

```bash
# 터미널 1: API
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload

# 터미널 2: 웹
cd frontend
cp .env.example .env
npm install
npm run dev
```

기본 주소는 웹 `http://localhost:5173`, API 문서 `http://localhost:8000/docs`다.

AI 상담과 선택 상권·업소 웹 리서치를 사용하려면 저장소 루트의 `.env.example`을 참고해 서버 실행 환경에 `OPENAI_API_KEY`를 설정한다. 기본 모델은 `gpt-5.4-mini`이며 `OPENAI_MODEL`로 변경할 수 있다. API 키가 없거나 OpenAI API가 일시적으로 실패하면 기존 추천 데이터와 API는 정상 동작하지만 AI 상담·웹 리서치는 재시도 오류를 반환한다.

대화와 추천 상태는 브라우저 탭의 `sessionStorage`에만 저장된다. 서버는 대화 원문을 저장하지 않고 Agents SDK 추적과 OpenAI 응답 저장을 비활성화한다.

대화창은 추천 상담과 별도로 결정론적 상권 통계 조회를 지원한다. 오른쪽 결과 영역은 `일반조회`, `창업맥락/전략가설`, `입지분석`의 세 페이지로 나뉘며 새 분석 종류에 따라 해당 페이지로 자동 전환된다. 이 세 페이지와 입지분석 안의 `상권분석`은 하나의 입지 AI와 대화 기록을 이어서 사용한다. `입지분석` 안은 다시 `상권분석`, `상권내 점포 분석`, `자금계획`으로 분리되어 지도·추천·보고서, 상권 내부 업소, 임대매물·정책자금 화면을 각각 독립적으로 보여준다. `상권내 점포 분석`과 `자금계획`만 별도 전용 AI와 독립 대화 기록을 사용하며 각 AI에는 현재 페이지의 축약된 분석 맥락만 전달된다. 상권·업종·자치구·행정동을 최근 매출, 폐업률, 개업률, 매출 성장률, 점포 수·밀도, 유동·상주·직장인구 기준으로 Top 1~50 오름차순/내림차순 조회할 수 있다. 결과에는 필터 적용 후 전체 조회 대상의 평균·중앙값·모집단 표준편차와 각 순위 값의 평균/중앙값 대비 차이·표준편차 거리도 포함한다. 상권·자치구 순위는 추천지도와 같은 메인 지도 영역에 조회 경계를 표시하며, 결과 행이나 경계를 선택하면 현재 조회 지표의 값·순위·평균/중앙값 대비 차이·표준편차 거리를 확인할 수 있다. 업종·행정동 순위는 목록으로만 표시한다. 예: `매출 높은 상권 5곳`, `가장 매출 높은 업종 10개`, `강남구 역삼1동에서 폐업률 높은 업종 5개`. 동 단위는 원천 데이터의 상권별 대표 행정동 기준이며 법정동 경계 집계가 아니다.

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
```

- `GET /api/v1/areas/{area_code}/stores?industry_code={code}`: 선택 상권 업소와 관계별 요약 조회
- `POST /api/v1/market-geographies`: 단순조회 상권·자치구 결과의 지도 경계 조회(최대 50개)
- `POST /api/v1/agent/workspace-turns`: 점포분석·자금계획 페이지별 독립 AI 대화
- 원본 조회는 24시간 메모리 캐시하며 외부 API 장애 시 프로세스에 남은 7일 이내 결과를 경고와 함께 사용한다.
- API 키가 없어도 기존 상권 추천은 정상 동작하고 점포 상세 조회만 503 오류를 반환한다.

상권 상세 화면의 `상권 최신 정보 검색`과 업소 상세의 `이 업소 웹 정보 검색`은 사용자가 누른 경우에만 OpenAI 웹 검색을 실행한다. 결과는 검색시각과 출처 링크를 포함해 해당 브라우저의 `sessionStorage`에만 저장하며 서버 캐시나 벡터 데이터베이스에는 적재하지 않는다. 웹 검색에는 `OPENAI_API_KEY`가 필요하고 제한 시간은 `WEB_RESEARCH_TIMEOUT_SECONDS`로 조정한다.

### 외부 임대매물·금융지원 1차 계획

2단계 상권 점포 화면에서 주변 경쟁점·보완업종을 검토한 뒤 `임대매물 추가`로 사용자가 직접 찾은 실제 매물을 후보함에 넣는다. 한 상권에 여러 후보를 저장하고 보증금, 월 고정 임차비, 권리금, 첫해 임차 현금 필요액을 비교한 뒤 한 건을 3단계 금융계획 대상으로 선택한다. 후보는 브라우저 탭의 `sessionStorage`에만 저장되며 추천 조건을 새로 확정하거나 전체 초기화하면 함께 제거된다.

매물은 수동으로 입력할 수 있고, 외부 URL 또는 보이는 매물 설명이 있으면 AI가 주소, 보증금, 월세, 관리비, 권리금, 임대면적, 층을 먼저 채운다. 빈 관리비·권리금은 `미확인`으로 유지하고 사용자가 0을 입력한 경우에만 비용 없음으로 확정한다. 미확인 비용이 있으면 비교 합계와 금융계획 생성을 차단한다. 추출값은 계약정보로 간주하지 않으며 사용자가 직접 확인·수정한다. URL 수집은 공개 HTTP(S) HTML·텍스트만 허용하고 사설망·루프백 주소, 인증정보 포함 URL, 1MB 초과 응답을 거부한다. 동적 렌더링이나 로그인 때문에 URL을 읽지 못하면 매물 설명을 붙여넣는다.

자금계획은 `보증금 + 권리금 + 12개월치 월세·관리비 + 인테리어·설비·초도물품·운영자금·기타 비용`으로 첫해 현금 필요액을 계산하고 자기자금과의 차이를 보여준다. 부가세, 공과금, 중개보수는 포함하지 않는다. 금융지원 후보는 AI가 결정하지 않으며 PostgreSQL 카탈로그의 자격조건에 입력한 소상공인 여부, 사업상태·업력, 융자제외 업종 여부를 결정론적으로 적용한다. 미입력 조건은 탈락시키지 않고 추가 확인사항으로 돌려준다. 현재 검수 카탈로그 기준일은 2026-07-24이며, 결과는 승인 가능성이 아니라 `기본조건 부합`, `추가 확인 필요`, `입력조건상 비대상`의 1차 후보다.

- `POST /api/v1/lease-candidates/extract`: URL·본문에서 확인용 임대매물 필드 추출
- `POST /api/v1/finance/plans`: 확인된 매물의 첫해 필요자금과 DB 금융지원 상품 후보 계산
- 상품 범위: KB국민은행 5종, 소상공인 정책자금 11종, 서울시 중소기업육성자금 16종, 보증 연계 사업 1종
- OpenAI 추출 제한 시간은 `LISTING_EXTRACTION_TIMEOUT_SECONDS`로 조정한다.

### 금융지원 상품 카탈로그 DB

은행대출·정책자금·지원사업·보증상품의 현재 정보를 담기 위한 PostgreSQL 스키마가
준비되어 있다. 초기 33개 검수 데이터와 기업마당 API 수집 결과를 preview한 뒤
승인 반영하는 적재 도구를 제공한다. `POST /api/v1/finance/plans`는 현재 DB의
`active`, `upcoming`, `unknown` 상품을 읽어 구조화된 자격조건을 결정론적으로
비교하고, 프런트엔드는 상품 유형·혜택·확인사항·공식 출처를 카드로 표시한다.

로컬 DB와 최초 스키마를 준비한다.

```bash
cp .env.docker.example .env.docker
cp .env.postgres.example .env.postgres
# 최초 실행 전에 두 파일의 PostgreSQL 비밀번호를 같은 임의 값으로 변경
docker compose up -d db
docker compose run --rm backend alembic -c backend/alembic.ini upgrade head
docker compose run --rm backend alembic -c backend/alembic.ini current
```

호스트에서 직접 실행할 때는 `.env.example`의 `DATABASE_URL`을 사용한다.

```bash
.venv/bin/alembic -c backend/alembic.ini upgrade head
```

- 추천 모델과 서울 상권 데이터는 기존 Parquet 아티팩트를 계속 사용한다.
- PostgreSQL은 금융지원 기관·상품·혜택·자격조건·공식 출처 카탈로그만 담당한다.
- 자격조건 그룹 간에는 OR, 한 그룹 안의 조건 간에는 AND 의미를 갖는다.
- 상품 조건 변경 시 과거 리비전을 만들지 않고 현재 행과 확인시각을 갱신한다.

초기 검수 카탈로그에는 2026-07-24 공식 안내 기준으로 KB국민은행 5종, 소상공인
정책자금 11종, 서울시 중소기업육성자금 16종, 신용보증재단중앙회 보증 연계 사업
1종이 정의되어 있다. 금액·금리 등 공식 원문에서 구조적으로 확정하지 못한 값은
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
- 시간 감쇠 설정: `0.94 ** quarter_age`(모델 노트북에서 적용)
- 향후 외부 검증: 2026Q1(필수 데이터 전체 확보 전까지 비활성)

기간은 [config/datasets.yaml](config/datasets.yaml)에서 변경한다. 2024년 전후 공간 단위 호환성은 병합 전 `check_historical_compatibility.py`로 반드시 검토한다.

## 환경 설정

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# .env에 SEOUL_API_KEY 입력
```

`.env`와 API 키는 Git에 포함하지 않으며, API 키는 로그·CSV·메타데이터에 저장하지 않는다.

## 원본 데이터 수집

`data/raw/sales/`의 2021~2025 연도별 추정매출 CSV는 기본적으로 재사용하며 변경하지 않는다. `--all`은 sales를 검증 대상으로만 표시하고 API 다운로드를 건너뛴다.

```bash
.venv/bin/python scripts/download_seoul_data.py \
  --dataset stores --quarters 20211 --debug-api

.venv/bin/python scripts/download_seoul_data.py \
  --all --skip-sales
```

`--debug-api`는 첫 5행 응답만 진단하고 파일을 저장하지 않는다. 전체 수집이 중간에 실패하면 같은 `--all --skip-sales` 명령을 다시 실행하면 이미 저장된 파일을 건너뛰고 이어받는다.

추정매출 API 재수집은 아래처럼 데이터셋과 덮어쓰기 의도를 둘 다 명시해야 한다. 기존 연도별 파일은 수정하지 않고 `sales_YYYYQ.csv`를 별도 생성한다.

```bash
.venv/bin/python scripts/download_seoul_data.py --dataset sales --overwrite
```

분기 파일은 `data/raw/<dataset>/<prefix>_20211.csv`, 비분기 영역 데이터는 `data/raw/area/area.csv`로 저장된다. 각 CSV 옆에 인증 정보가 없는 `.meta.json`이 생성된다.

`--debug-api`는 HTTP 상태, Content-Type, 본문 길이·앞 500자, redirect, JSON 최상위 키, total count와 첫 페이지 행 수를 출력한다. URL·본문·예외의 API 키는 `***MASKED***`로 치환되며, 진단 모드에서는 raw 파일을 저장하지 않는다.

## 검증과 interim 생성

```bash
.venv/bin/python scripts/check_raw_data.py
.venv/bin/python scripts/check_historical_compatibility.py
.venv/bin/jupyter nbconvert --to notebook --execute \
  notebooks/01_ingest_clean.ipynb \
  --output 01_ingest_clean.executed.ipynb
```

검증 결과는 `outputs/tables/`의 인벤토리·스키마·중복·분기 커버리지·코드 교집합·연도별 분포 보고서로 저장된다. 필수 데이터가 없으면 `check_raw_data.py`는 보고서를 남긴 후 종료 코드 1을 반환한다.

노트북 실행 순서:

1. `notebooks/00_data_inventory.ipynb`
2. `notebooks/01_ingest_clean.ipynb`
3. `notebooks/02_build_area_profile.ipynb`
4. `notebooks/03_build_industry_performance.ipynb`
5. `notebooks/04_success_reference_knn.ipynb`
6. `notebooks/05_time_validation.ipynb`
7. `notebooks/06_export_recommendations.ipynb`

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

## 정적 검사

```bash
.venv/bin/python -m compileall src scripts
.venv/bin/python -m pytest -q
.venv/bin/jupyter nbconvert --to notebook --execute notebooks/00_data_inventory.ipynb \
  --output 00_data_inventory.executed.ipynb
```

모든 `api_service_name`은 서울 열린데이터광장의 각 OA 데이터셋 OpenAPI 명세에서 확인한 값이다. 분기 경로 필터를 공식으로 제공하지 않는 서비스는 전체 페이지를 수집한 뒤 `STDR_YYQU_CD`로 로컬 필터링·분할한다.
