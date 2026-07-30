# 배포 구성

프런트엔드와 백엔드는 독립적으로 배포한다.

## 협업용 Docker Compose

서버 배포 전 로컬 협업 환경은 저장소 루트의 `compose.yaml`을 사용한다. PostgreSQL은
금융지원 상품 카탈로그를 담당하고, 백엔드는 FastAPI 개발 서버, 프런트엔드는 Vite
개발 서버로 실행해 코드 변경을 바로 반영한다.

처음 실행:

```bash
cp .env.docker.example .env.docker
cp .env.postgres.example .env.postgres
# 최초 실행 전에 두 파일의 PostgreSQL 비밀번호를 같은 임의 값으로 변경
docker compose up --build
docker compose run --rm backend alembic -c backend/alembic.ini upgrade head
```

기본 접속 주소:

- 웹: `http://localhost:5173`
- API 상태: `http://localhost:8000/api/v1/health/live`
- API 문서: `http://localhost:8000/docs`
- PostgreSQL: `localhost:5432` (`.env.postgres` 사용, 호스트 루프백에서만 접근 가능)

자주 쓰는 명령:

```bash
docker compose up
docker compose up --build
docker compose down
docker compose logs -f backend
docker compose logs -f frontend
```

AI 상담, 웹 검색, 상권 내 점포 조회까지 확인하려면 `.env.docker`에 아래 값을 채운다.
비워 두어도 기본 추천 API와 화면 개발은 가능하다.

```bash
OPENAI_API_KEY=<OpenAI API 키>
DATA_GO_KR_SERVICE_KEY=<공공데이터포털 인증키>
```

`frontend` 서비스는 컨테이너 시작 시 `npm ci`를 실행하고, `node_modules`는 Docker named
volume에 저장한다. 프런트 의존성이 꼬이면 아래처럼 볼륨까지 지운 뒤 다시 띄운다.

```bash
docker compose down -v
docker compose up --build
```

## Frontend

- 빌드 위치: `frontend/`
- 빌드 명령: `npm ci && npm run build`
- 배포 디렉터리: `frontend/dist/`
- 필수 변수: `VITE_API_BASE_URL`
- 지도 변수: `VITE_MAP_TILE_URL`, `VITE_MAP_ATTRIBUTION`

SPA fallback을 지원하는 정적 호스팅/CDN을 사용한다. 컨테이너 배포가 필요한 경우
`frontend/Dockerfile`을 사용한다.

## Backend

- 빌드 컨텍스트: 저장소 루트
- Dockerfile: `backend/Dockerfile`
- 컨테이너 포트: `8000`
- readiness: `/api/v1/health/ready`
- liveness: `/api/v1/health/live`
- 필수 변수: `APP_ENV=production`, `CORS_ORIGINS=https://<frontend-domain>`, `OPENAI_API_KEY`
- 에이전트 변수: `OPENAI_MODEL=gpt-5.4-mini`, `AGENT_TIMEOUT_SECONDS=30`, `AGENT_MAX_TURNS=4`, `AGENT_RATE_LIMIT_PER_MINUTE=10`
- 외부 점포 API 보호: `STORE_RATE_LIMIT_PER_MINUTE=5`(클라이언트별 1분 GET 한도)

배포 시 `backend/artifacts/current`가 이미지에 포함되므로 모델과 데이터 버전은 이미지
태그와 함께 불변으로 관리한다. API 키나 비밀값은 이미지와 Git에 포함하지 않는다.
`OPENAI_API_KEY`는 배포 플랫폼의 비밀 저장소에서 런타임 환경변수로만 주입한다.
