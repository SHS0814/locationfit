# KB AI Challenge — 대화형 AI 입지 추천

선택 업종의 과거 성과가 우수했던 상권을 참조 집단으로 정의하고, 구조적으로 유사한 후보를 가중 KNN으로 탐색한 뒤 신뢰도 보정 과거 성과를 결합한다.

예비 창업자는 자연어로 업종·지역·고객·운영 맥락을 설명할 수 있다. 상담 에이전트는 필요한 질문만 최대 4회 진행한 뒤 현재 데이터에서 시장 범위와 제약 충돌을 탐색하고, 조건 충실형·성장 기회형·안정성 우선형 가설을 비교한다. 사용자가 전략과 조건을 명시적으로 확인하면 결정론적 추천 엔진을 실행한다. AI는 점수와 매출을 생성하거나 재계산하지 않는다.

## 웹서비스 구조

웹서비스는 `frontend/`와 `backend/`를 명시적으로 분리한다.

- `frontend/`: React, Vite, TypeScript 기반 대화·맥락/가정·전략 비교·결과 목록·지도
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

AI 상담을 사용하려면 저장소 루트의 `.env.example`을 참고해 서버 실행 환경에 `OPENAI_API_KEY`를 설정한다. 기본 모델은 `gpt-5.4-mini`이며 `OPENAI_MODEL`로 변경할 수 있다. API 키가 없거나 OpenAI API가 일시적으로 실패하면 기존 추천 데이터와 API는 정상 동작하지만 대화형 상담은 재시도 오류를 반환한다.

대화와 추천 상태는 브라우저 탭의 `sessionStorage`에만 저장된다. 서버는 대화 원문을 저장하지 않고 Agents SDK 추적과 OpenAI 응답 저장을 비활성화한다.
서비스 아티팩트를 다시 만들려면 저장소 루트에서 아래 명령을 실행한다.

```bash
.venv/bin/python backend/pipelines/scripts/build_service_artifacts.py
```

- 기존 API 기본값 `balanced`: 상권 구조 적합도 60%, 신뢰도 보정 과거 성과 40%
- `condition_fit`: 조건 적합 75%, 성과 근거 25%
- `growth`: 조건 적합 45%, 성장 중심 성과 근거 55%
- `stability`: 조건 적합 45%, 안정성 중심 성과 근거 55%

상담 중 서울 열린데이터 API를 실시간 호출하지 않으며 배포 아티팩트만 읽는다. 상가 임대료·보증금은 아직 추천에 사용하지 않고 `CommercialCostProvider` 확장 지점과 데이터 공백 안내만 제공한다.

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
