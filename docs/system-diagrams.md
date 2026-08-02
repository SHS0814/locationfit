# KB AI Challenge — 유스케이스 및 시스템 아키텍처

> 이 문서는 [프로젝트 기술명세서](./project-technical-spec.md)를 보완하는 시각화 문서다.  
> 다이어그램은 현재 저장소의 FastAPI, React, 추천 아티팩트 및 AI 상담 구현을 기준으로 작성했다.

## 1. 시스템 경계

서비스의 핵심 사용자는 서울에서 창업 입지를 탐색하는 예비 창업자다. 사용자는 웹 화면 또는 API를 통해 조건을 입력하고, AI와 상담하거나 결정론적 추천 엔진을 직접 호출할 수 있다.

외부 시스템은 다음 네 종류로 구분한다.

- 서울 열린데이터광장: 상권 구조·매출·인구·점포·시설 데이터 수집
- 공공데이터포털 소상공인시장진흥공단 API: 선택 상권 안의 현재 영업 점포 조회
- OpenAI API: 자연어 상담, 추천 결과 설명, 사용자 요청 시 웹 리서치
- PostgreSQL: 정책자금 카탈로그 저장과 금융계획 조회

추천 모델 자체는 운영 요청 중 외부 API나 데이터베이스를 호출하지 않는다. 빌드 시점에 생성한 Parquet 아티팩트를 메모리에 올려 사용한다.

---

## 2. 전체 유스케이스 다이어그램

Mermaid에는 UML 전용 유스케이스 문법이 없으므로, 액터와 시스템 경계를 flowchart로 표현했다. 타원형 노드는 사용자가 달성하려는 유스케이스를 의미한다.

```mermaid
flowchart LR
    founder["👤 예비 창업자"]
    operator["👤 데이터·서비스 운영자"]
    seoul["서울 열린데이터광장"]
    sbiz["소상공인시장진흥공단 API"]
    openai["OpenAI API"]
    postgres[("PostgreSQL")]

    subgraph system["KB 대화형 AI 상권추천 시스템"]
        direction TB

        subgraph discovery["입지 탐색"]
            uc1(["자연어로 창업 계획 상담"])
            uc2(["추천 조건 직접 입력"])
            uc3(["시장 범위·제약 충돌 확인"])
            uc4(["조건·성장·안정 전략 비교"])
            uc5(["추천 조건 최종 확인"])
        end

        subgraph recommendation["상권 추천·설명"]
            uc6(["상권 추천 실행"])
            uc7(["추천 근거와 위험요인 확인"])
            uc8(["후보 상권 비교"])
            uc9(["상권·자치구 순위 조회"])
            uc10(["지도에서 실제 경계 확인"])
        end

        subgraph followup["후속 창업 분석"]
            uc11(["상권 내 영업 점포 분석"])
            uc12(["상권·업소 웹 정보 검색"])
            uc13(["임대매물 후보 관리"])
            uc14(["임대료·초기 현금 비교"])
            uc15(["정책자금·자금계획 확인"])
        end

        subgraph operation["데이터·운영 관리"]
            uc16(["서울시 원천데이터 수집"])
            uc17(["데이터 품질 검증"])
            uc18(["추천 아티팩트 빌드"])
            uc19(["임대시세 갱신"])
            uc20(["정책자금 카탈로그 갱신"])
            uc21(["서비스 준비 상태 확인"])
        end
    end

    founder --> uc1
    founder --> uc2
    founder --> uc3
    founder --> uc4
    founder --> uc5
    founder --> uc6
    founder --> uc7
    founder --> uc8
    founder --> uc9
    founder --> uc10
    founder --> uc11
    founder --> uc12
    founder --> uc13
    founder --> uc14
    founder --> uc15

    operator --> uc16
    operator --> uc17
    operator --> uc18
    operator --> uc19
    operator --> uc20
    operator --> uc21

    seoul --> uc16
    sbiz --> uc11
    openai --> uc1
    openai --> uc12
    postgres --> uc15
    postgres --> uc20

    uc1 -. "조건 초안 생성" .-> uc3
    uc3 -. "include" .-> uc4
    uc4 -. "사용자 선택" .-> uc5
    uc5 -. "확인 후에만 실행" .-> uc6
    uc6 -. "extend" .-> uc7
    uc7 -. "extend" .-> uc8
    uc6 -. "결과 경계" .-> uc10
    uc10 -. "상권 선택" .-> uc11
    uc11 -. "선택 실행" .-> uc12
    uc11 -. "후보 조사" .-> uc13
    uc13 -. "include" .-> uc14
    uc14 -. "대상 매물 선택" .-> uc15

    uc16 -. "선행" .-> uc17
    uc17 -. "검증 통과" .-> uc18
    uc19 -. "아티팩트 추가" .-> uc18
```

### 2.1 주요 액터

| 액터 | 책임과 관심사 |
|---|---|
| 예비 창업자 | 조건 입력, 전략 선택, 추천 확인, 후보 비교, 점포·임대·자금 검토 |
| 데이터·서비스 운영자 | 원천 수집, 품질 보고서 검토, 아티팩트 빌드·배포, readiness 확인 |
| 서울 열린데이터광장 | 분기별 상권·매출·점포·인구·시설 원천 제공 |
| 소상공인시장진흥공단 API | 선택한 실제 상권 경계 안의 현재 영업 점포 제공 |
| OpenAI API | 자연어 상담과 사용자 요청에 의한 웹 리서치 수행 |
| PostgreSQL | 검수된 정책자금 카탈로그 영속화 |

### 2.2 핵심 유스케이스 명세

| ID | 유스케이스 | 선행 조건 | 정상 결과 | 주요 예외 |
|---|---|---|---|---|
| UC-01 | 자연어 창업 상담 | AI API 설정 | 조건 초안·가정·다음 질문 생성 | API 키 없음, 제한 시간 초과 |
| UC-02 | 추천 조건 직접 입력 | 유효한 업종코드 | 구조화된 추천 요청 생성 | 스키마 범위 위반, 없는 코드 |
| UC-03 | 전략 시나리오 비교 | 업종과 기본 조건 확보 | 조건·성장·안정 전략 결과 비교 | 적격 후보 부족 |
| UC-04 | 추천 조건 확인 | 실행 가능한 조건 초안 | 확정 요청으로 추천 엔진 1회 실행 | 잘못된 상담 상태 |
| UC-05 | 상권 추천 | 아티팩트 readiness 통과 | 순위·점수·근거·경계 반환 | 후보 없음, 아티팩트 오류 |
| UC-06 | 추천 결과 설명 | 활성 추천 결과 존재 | 관측 지표 기반 설명·비교 | 결과에 없는 상권 요청 |
| UC-07 | 상권 내 점포 조회 | 상권과 업종 선택, 외부 API 키 | 경계 내부 점포 분류·표시 | 외부 API 장애, 캐시 없음 |
| UC-08 | 웹 리서치 | 사용자가 명시적으로 실행 | 검색 시각·출처 링크가 있는 요약 | AI API 장애·시간 초과 |
| UC-09 | 임대매물 비교 | 사용자가 찾은 매물 정보 | 보증금·월 임차비·권리금·첫해 현금 비교 | 필수 금액 누락 |
| UC-10 | 금융계획 | 분석할 임대 후보 선택 | 정책자금 후보와 자금계획 제공 | 카탈로그 DB 준비 실패 |
| UC-11 | 아티팩트 빌드 | 원천·processed 데이터 검증 통과 | 버전·체크섬이 있는 배포 묶음 생성 | 경계 불일치, 필수 컬럼 누락 |

---

## 3. 추천 상담 유스케이스 상세 흐름

```mermaid
sequenceDiagram
    autonumber
    actor U as 예비 창업자
    participant FE as React Web
    participant API as FastAPI
    participant AI as LocationAgentService
    participant LLM as OpenAI Agent
    participant REC as RecommenderService

    U->>FE: 창업 계획을 자연어로 입력
    FE->>API: POST /api/v1/agent/turns<br/>action=message
    API->>AI: 대화 기록·조건 초안·창업 맥락 전달
    AI->>LLM: 구조화된 AgentDecision 요청
    LLM-->>AI: 조건 초안·가정·부족 필드·응답
    AI->>REC: 시장 범위와 전략 시나리오 조회
    REC-->>AI: 후보 수·전략별 Top 후보·제약 충돌
    AI-->>API: phase와 조건 카드
    API-->>FE: scenarios_ready 또는 ready_for_confirmation
    FE-->>U: 전략 비교와 확인 요청 표시

    U->>FE: 조건·전략 확인
    FE->>API: POST /api/v1/agent/turns<br/>action=confirm_recommendation
    API->>AI: 확정된 RecommendationDraft
    AI->>REC: recommend_with_report() 1회
    REC-->>AI: 추천·진단·Top 3 비교 보고서
    AI-->>API: phase=results
    API-->>FE: 추천 목록·지도 경계·보고서
    FE-->>U: 1위 핵심 이유와 대안 후보 표시

    opt 추천 결과 후속 질문
        U->>FE: 특정 상권의 위험요인 질문
        FE->>API: 활성 추천 요청과 질문 전달
        API->>AI: explain_recommended_areas 도구 제공
        AI->>REC: 선택 상권의 검증된 근거 조회
        REC-->>AI: 매출·성장·안정·경쟁·품질 수치
        AI-->>FE: 관측 근거를 사용한 설명
    end
```

### 3.1 성공 조건

- 추천 실행 전 사용자가 조건과 전략을 명시적으로 확인한다.
- AI가 아닌 `RecommenderService`가 점수와 순위를 계산한다.
- 응답은 실행한 아티팩트 버전과 실제 적용 가중치를 포함한다.
- 후속 설명은 현재 추천 결과와 관측 근거만 사용한다.
- 같은 아티팩트와 같은 요청은 같은 순위와 점수를 반환한다.

### 3.2 실패 및 대체 흐름

| 상황 | 처리 |
|---|---|
| AI API 키 없음·외부 장애 | AI 상담은 503, 직접 추천 API는 계속 사용 가능 |
| AI 제한 시간 초과 | 504 `AGENT_TIMEOUT`; 추천 엔진 상태에는 영향 없음 |
| 후보가 0개 | 422 `NO_ELIGIBLE_CANDIDATES`; 제약 완화 선택지 제시 가능 |
| 사용자가 확인 없이 실행 요구 | 상담 상태를 유지하고 확인 가능한 조건 카드 제시 |
| 임대료 아티팩트 없음 | 기존 추천 유지, `budget_adjusted=false`와 원인 반환 |
| 점포 외부 API 장애 | 프로세스 내 7일 이내 stale 캐시가 있으면 경고와 함께 사용 |

---

## 4. 논리 시스템 아키텍처

```mermaid
flowchart TB
    subgraph client["Client Layer"]
        browser["브라우저"]
        react["React + TypeScript SPA"]
        session["sessionStorage<br/>대화·추천·임대후보 상태"]
        map["추천·시장조회 지도"]
        browser --> react
        react <--> session
        react --> map
    end

    subgraph api["API Layer — FastAPI /api/v1"]
        middleware["RequestContext<br/>크기 제한·요청 ID·처리시간"]
        ratelimit["추천·AI Rate Limit"]
        routers["health · metadata · recommendations<br/>market · stores · agent · research · finance"]
        schemas["Pydantic Request/Response Schemas"]
        errors["표준 오류 응답"]

        middleware --> ratelimit --> routers --> schemas
        schemas --> errors
    end

    subgraph services["Application Service Layer"]
        recommender["RecommenderService"]
        locationAgent["LocationAgentService"]
        workspaceAgent["WorkspaceAgentService"]
        marketLookup["MarketLookupService"]
        storeService["CommercialStoreService"]
        researchService["WebResearchService"]
        leaseService["LeaseCandidateService"]
        financeService["FinancePlanService"]
        costProvider["CommercialCostProvider"]
    end

    subgraph domain["Domain / Model Layer"]
        areaRec["AreaRecommender<br/>가중 거리 + 성과 재순위화"]
        scoring["성과 백분위·신뢰도 보정"]
        reports["추천 비교 보고서"]
        areaRec --> scoring
        areaRec --> reports
    end

    subgraph artifacts["Read-only Service Artifacts"]
        manifest["manifest.json<br/>버전·기간·SHA-256"]
        index[("상권 추천 인덱스<br/>1,650행")]
        evidence[("상권×업종 근거<br/>26,810행")]
        boundaries[("상권·자치구 GeoJSON 경계")]
        rent[("임대시세<br/>14,791행")]
    end

    subgraph persistence["Persistence"]
        pg[("PostgreSQL<br/>정책자금 카탈로그")]
    end

    subgraph external["External Services"]
        openai["OpenAI API"]
        sbiz["소상공인시장진흥공단<br/>상가업소 API"]
        web["공개 웹 검색 결과"]
    end

    react -->|HTTPS / JSON| middleware
    routers --> recommender
    routers --> locationAgent
    routers --> workspaceAgent
    routers --> marketLookup
    routers --> storeService
    routers --> researchService
    routers --> leaseService
    routers --> financeService

    locationAgent -->|도구 호출| recommender
    locationAgent --> openai
    workspaceAgent --> openai
    researchService --> openai
    researchService --> web
    recommender --> areaRec
    recommender --> costProvider
    marketLookup --> index
    storeService --> sbiz
    financeService --> pg

    manifest --> recommender
    index --> areaRec
    evidence --> areaRec
    boundaries --> recommender
    rent --> costProvider
```

### 4.1 계층별 책임

| 계층 | 핵심 책임 | 하지 않는 일 |
|---|---|---|
| Client | 사용자 입력, 상태 유지, 지도·보고서 표시 | 추천 점수 재계산 |
| API | 계약 검증, 의존성 주입, 오류·요청 추적 | 데이터 특징 생성 |
| Application Service | 도메인 호출 조정, 경계·임대료·보고서 결합 | AI가 만든 수치를 신뢰해 순위에 사용 |
| Domain/Model | 후보 필터, 조건점수, 성과점수, 신뢰도 보정 | 외부 API·DB 직접 호출 |
| Artifact | 검증된 정적 추천 데이터 제공 | 요청 시 원천 데이터 갱신 |
| External/Persistence | AI·점포·정책자금 부가기능 제공 | 핵심 추천 엔진의 필수 의존성 역할 |

---

## 5. 데이터 파이프라인 아키텍처

```mermaid
flowchart LR
    subgraph sources["Sources"]
        seoulAPI["서울 열린데이터광장 API"]
        salesCSV["기존 연도별 추정매출 CSV"]
        areaSHP["상권 SHP<br/>EPSG:5181"]
        districtGeo["서울 25개 자치구 경계"]
        rentAPI["서울시 임대시세"]
    end

    subgraph raw["data/raw — 변경하지 않는 원천"]
        rawCSV["데이터셋별 CSV"]
        metadata["인증정보 없는 .meta.json"]
        rawShape["SHP / GeoJSON"]
        rawRent["시각별 임대시세 원본"]
    end

    subgraph validation["Validation"]
        inventory["필수 파일·스키마"]
        grain["grain 키·중복"]
        quarters["분기 커버리지"]
        codeJoin["상권코드 교집합"]
        history["연도별 분포·코드 유지율"]
    end

    subgraph interim["data/interim"]
        standardized["표준키 Parquet<br/>quarter · area_code · industry_code"]
        diagnostics["ingest_diagnostics.csv"]
    end

    subgraph features["Feature Engineering"]
        profile["area_profile.parquet<br/>분기×상권 구조"]
        perf["area_industry_evidence.parquet<br/>상권×업종 성과"]
        dictionaries["특징 사전·검증 보고서"]
        recIndex["area_recommendation_index.parquet<br/>최근 4분기 상권 대표값"]
    end

    subgraph build["Service Artifact Build"]
        crs["EPSG:5181 → EPSG:4326"]
        topology["make_valid · 정밀도 보정"]
        checksums["행 수·SHA-256 계산"]
        bundle["backend/artifacts/current"]
    end

    seoulAPI --> rawCSV
    seoulAPI --> metadata
    salesCSV --> rawCSV
    areaSHP --> rawShape
    districtGeo --> rawShape
    rentAPI --> rawRent

    rawCSV --> inventory --> grain --> quarters --> codeJoin --> history
    history --> standardized
    history --> diagnostics
    standardized --> profile
    standardized --> perf
    profile --> dictionaries
    perf --> dictionaries
    profile --> recIndex

    recIndex --> bundle
    perf --> bundle
    rawShape --> crs --> topology --> bundle
    rawRent --> bundle
    bundle --> checksums
    checksums --> bundle
```

### 5.1 파이프라인 단계별 산출물

| 단계 | 입력 | 출력 | 실패 기준 |
|---|---|---|---|
| 수집 | 서울시 API·기존 CSV | `data/raw` | HTTP 오류, 응답 스키마 불일치 |
| 원천 검증 | raw CSV | 품질 보고서 | 필수 파일·키·분기 누락 |
| 표준화 | 원천 한글/API 컬럼 | `data/interim/*.parquet` | grain 키 중복, 타입 변환 실패 |
| 상권 프로필 | 인구·점포·시설·주거 | `area_profile.parquet` | 상권 마스터 불일치, 면적 오류 |
| 업종 근거 | 매출·점포·상권 프로필 | `area_industry_evidence.parquet` | 필수 성과 컬럼 누락 |
| 추천 인덱스 | 최근 구조 프로필 | 상권별 1행 인덱스 | 최근 4분기 누락, 매출 특징 유입 |
| 공간 빌드 | SHP·GeoJSON | WGS84 경계 Parquet | 코드 집합·도형 유효성 불일치 |
| 패키징 | 추천·경계·임대 데이터 | manifest 포함 아티팩트 | 행 수·체크섬 생성 실패 |

---

## 6. 배포 아키텍처

```mermaid
flowchart TB
    user["사용자 브라우저"]

    subgraph host["서비스 실행 환경"]
        nginx["Nginx :8080 · UID 101<br/>정적 파일·SPA 라우팅 · 보안 헤더"]
        frontend["React Build Assets"]
        backend["FastAPI Container · UID 10001<br/>Uvicorn"]
        memory["Process Memory<br/>추천 인덱스·성과·경계"]
        artifactVolume["Read-only Artifact Directory"]
        database[("PostgreSQL<br/>정책 카탈로그·AI 요청 원장")]

        nginx --> frontend
        backend <--> memory
        artifactVolume -->|startup load| memory
        backend --> database
    end

    openai["OpenAI API"]
    dataGoKr["공공데이터포털 API"]

    user -->|HTTP/HTTPS| nginx
    frontend -->|/api/v1 JSON| backend
    backend -->|AI 상담·웹 리서치| openai
    backend -->|선택 상권 점포 조회| dataGoKr
```

### 6.1 기동과 readiness

```mermaid
sequenceDiagram
    participant O as Container Runtime
    participant API as FastAPI lifespan
    participant L as ArtifactLoader
    participant A as Artifact Directory
    participant H as Health API

    O->>API: 프로세스 시작
    API->>L: RecommenderService 초기화
    L->>A: manifest 및 필수 파일 확인
    L->>A: SHA-256·스키마·코드·경계 검증
    alt 검증 성공
        L-->>API: 메모리 객체 반환
        API->>API: recommender 등록
        H-->>O: /health/ready 200 + artifact_version
    else 검증 실패
        L-->>API: 오류
        API->>API: 내부 원인은 request ID와 함께 서버 로그에 기록
        H-->>O: /health/ready 503 + 일반화된 오류
    end
```

---

## 7. 신뢰 경계와 데이터 저장 위치

```mermaid
flowchart LR
    subgraph browserBoundary["브라우저 신뢰 경계"]
        ui["React UI"]
        ss[("sessionStorage")]
        ui <--> ss
    end

    subgraph apiBoundary["백엔드 신뢰 경계"]
        validation["Pydantic 검증"]
        deterministic["결정론적 추천 엔진"]
        cache["점포 API 메모리 캐시<br/>24시간 fresh / 7일 stale"]
        validation --> deterministic
    end

    subgraph dataBoundary["관리 데이터 경계"]
        artifact[("읽기 전용 Parquet")]
        db[("정책자금·AI 요청 원장 PostgreSQL")]
    end

    subgraph outside["외부 제공자"]
        ai["OpenAI"]
        store["상가업소 API"]
    end

    ui -->|검증 전 사용자 입력| validation
    deterministic --> artifact
    apiBoundary --> db
    apiBoundary -->|필요할 때만| ai
    store --> cache
    cache --> apiBoundary
```

| 데이터 | 저장 위치 | 지속 범위 | 비고 |
|---|---|---|---|
| 대화 원문·추천 UI 상태 | 브라우저 `sessionStorage` | 브라우저 탭 | 서버 DB에 저장하지 않음 |
| 추천 구조·성과·경계 | Parquet 아티팩트 | 배포 버전 | 읽기 전용, 체크섬 검증 |
| 점포 API 응답 | 백엔드 메모리 캐시 | 프로세스 수명 | 24시간 fresh, 최대 7일 stale fallback |
| 웹 리서치 결과 | 브라우저 `sessionStorage` | 브라우저 탭 | 사용자가 눌렀을 때만 실행 |
| 정책자금 카탈로그 | PostgreSQL | 영구 | preview·검증 후 반영 |
| AI 요청 제한 원장 | PostgreSQL | 일일 집계·실행 lease | 전역 요청·비용·동시 실행 제한, 대화 원문 미저장 |
| Agents SDK 응답 저장·추적 | 사용하지 않음 | 해당 없음 | `store=False`, tracing 비활성화 |

---

## 8. 다이어그램 해석 요약

1. **데이터 경로**는 수집 시점과 서비스 시점이 분리되어 있다. 운영 추천 요청은 서울시 API를 실시간 호출하지 않는다.
2. **추천 경로**는 Pydantic 검증을 거쳐 결정론적 모델로 들어가며 AI가 점수 계산에 참여하지 않는다.
3. **AI 경로**는 자연어 조건 수집과 결과 설명을 담당하고, 사용자 확인 후 검증된 추천 도구만 호출한다.
4. **부가기능 경로**는 점포·웹 리서치·금융지원으로 나뉘며 외부 서비스 장애가 핵심 추천 엔진으로 전파되지 않도록 분리되어 있다.
5. **운영 경로**는 manifest, SHA-256, readiness를 통해 잘못된 데이터 묶음으로 서비스가 시작되는 것을 차단한다.
