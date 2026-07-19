# 배포 구성

프런트엔드와 백엔드는 독립적으로 배포한다.

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

배포 시 `backend/artifacts/current`가 이미지에 포함되므로 모델과 데이터 버전은 이미지
태그와 함께 불변으로 관리한다. API 키나 비밀값은 이미지와 Git에 포함하지 않는다.
`OPENAI_API_KEY`는 배포 플랫폼의 비밀 저장소에서 런타임 환경변수로만 주입한다.
