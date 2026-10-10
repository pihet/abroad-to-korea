# infra — 배포·운영

전체 실행은 루트의 `docker compose up --build -d`. 자세한 운영 방법은 `docs/INFRASTRUCTURE.md`.

| 폴더 | 역할 |
|---|---|
| `docker/` | 보조 서비스 이미지: `Dockerfile.airflow`, `Dockerfile.minio`, `Dockerfile.mlflow`. 개발·API 패키지는 루트 `requirements.txt` 하나로 관리하고, 서비스 전용 패키지는 각 이미지에 고정한다. 빌드 context는 저장소 루트 (API 이미지는 루트 `Dockerfile`) |
| `airflow/dags/` | 배치 스케줄: 매일 TourAPI 수집, DB 게시, 사진 캐시, 만료 사진 정리 |
| `migrations/`, `alembic.ini` | DB 스키마 변경 이력. `alembic -c infra/alembic.ini upgrade head` (Compose의 `migrate` 서비스가 실행) |
| `postgres/init/` | 빈 볼륨에서 처음 한 번 DB·계정 생성 |
| `mlflow/` | MLflow 서버 시작 스크립트 |
