# AI 에이전트 아키텍처 — 발표용

> 하나의 서비스 안에서 입지 선정부터 점포 검토, 자금계획까지 3개의 전문 AI 에이전트가 역할을 나눠 지원한다.

## 전체 구조

```mermaid
flowchart TB
    USER["사용자"] --> WEB["React 웹 서비스<br/>화면과 대화 상태 관리"]

    subgraph AGENTS["3개의 전문 AI 에이전트"]
        direction LR
        LOCATION["입지 상담 AI<br/>조건 이해 · 상권 추천"]
        STORE["점포분석 AI<br/>경쟁점 · 주변 업소 분석"]
        FINANCE["자금계획 AI<br/>필요자금 · 정책지원 검토"]
    end

    WEB --> LOCATION
    WEB --> STORE
    WEB --> FINANCE

    LOCATION --> SDK["OpenAI Agents SDK<br/>대화 이해 · 도구 선택 · 답변 생성"]
    STORE --> SDK
    FINANCE --> SDK

    SDK -->|"입지 도구"| RECOMMENDER["추천·상권 통계 서비스"]
    SDK -->|"점포 도구"| STORE_SERVICE["점포 조회·웹 리서치 서비스"]
    SDK -->|"자금 도구"| FINANCE_SERVICE["자금 계산·정책상품 판정 서비스"]

    RECOMMENDER --> MARKET_DATA["서울 상권 데이터<br/>Parquet"]
    STORE_SERVICE --> STORE_DATA["상가업소 API<br/>웹 검색"]
    FINANCE_SERVICE --> FINANCE_DATA["금융상품 카탈로그<br/>PostgreSQL"]

    classDef user fill:#fff7ed,stroke:#ea580c,color:#7c2d12,stroke-width:2px;
    classDef app fill:#eff6ff,stroke:#2563eb,color:#1e3a8a,stroke-width:2px;
    classDef agent fill:#f5f3ff,stroke:#7c3aed,color:#4c1d95,stroke-width:2px;
    classDef sdk fill:#ecfdf5,stroke:#059669,color:#064e3b,stroke-width:2px;
    classDef service fill:#f8fafc,stroke:#475569,color:#0f172a;
    classDef data fill:#fefce8,stroke:#ca8a04,color:#713f12;

    class USER user;
    class WEB app;
    class LOCATION,STORE,FINANCE agent;
    class SDK sdk;
    class RECOMMENDER,STORE_SERVICE,FINANCE_SERVICE service;
    class MARKET_DATA,STORE_DATA,FINANCE_DATA data;
```

## 발표 핵심 메시지

1. **역할 분리:** 입지·점포·자금계획을 각각 전문 에이전트가 담당한다.
2. **도구 기반 검증:** AI가 수치를 만들지 않고 검증된 서비스와 데이터를 조회한다.
3. **상태 격리:** 화면별 대화와 분석 범위를 분리해 다른 단계의 정보가 섞이지 않는다.

## 30초 설명

사용자가 웹에서 질문하면 현재 화면에 맞는 전문 에이전트가 선택됩니다. 각 에이전트는 OpenAI Agents SDK를 통해 필요한 도구를 호출하고, 추천·점포·금융 서비스가 실제 데이터로 결과를 계산합니다. 따라서 AI는 대화와 도구 선택을 담당하고, 핵심 수치와 판정은 결정론적 서비스가 담당합니다.
