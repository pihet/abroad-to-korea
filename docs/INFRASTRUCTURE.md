# 데이터 인프라 운영

## 구성

전체 서비스는 단일 호스트의 Docker Compose에서 실행한다.

- `api`: FastAPI 서비스, 추천·지역 정보·회원·사진 보관 API
- `postgres`: 하나의 PostgreSQL 인스턴스 안에 서비스·Airflow·MLflow DB를 분리, `pgvector` 포함
- `redis`: 로그인 세션·OAuth state·호출 제한·검색 결과 캐시
- `minio`: 사용자 사진, `bronze/` 원본 응답, 관광지 사진 파일
- `migrate`: API 시작 전에 Alembic 스키마를 적용하고 종료하는 일회성 컨테이너
- `airflow-init`: Airflow 메타 DB와 TourAPI pool을 준비하고 종료하는 일회성 컨테이너
- `airflow-api-server`, `airflow-dag-processor`, `airflow-scheduler`: DAG 파싱·등록과 LocalExecutor 기반 배치 운영
- `mlflow`: CLIP·혼잡도 실험의 parameter, metric, artifact와 Git commit 추적

PostgreSQL이 회원·저장 지역·수집 데이터의 원본이다. Redis 값은 삭제되어도 다시 로그인하거나 재계산할 수 있어야 한다. MinIO 데이터는 DB의 객체 키와 함께 백업해야 한다.

회원 이메일은 대소문자를 무시하고 하나만 허용한다. 검증된 OAuth 이메일이 기존 검증 계정과 같으면 로그인 수단을 같은 회원에 연결한다. 이메일 인증 없이 가입한 계정은 계정 선점을 막기 위해 먼저 비밀번호로 로그인한 뒤 Google·Kakao를 명시적으로 연결해야 한다.

## 외부 접속 주소

| 대상 | 주소 | 비고 |
|---|---|---|
| 웹/API | `http://localhost:8000` | API 문서는 `/docs` |
| Airflow | `http://localhost:8080` | DAG 확인·실행 |
| MLflow | `http://localhost:5000` | 실험 run·지표·artifact 비교 |
| PostgreSQL | `127.0.0.1:5434` | 컨테이너 내부에서는 `postgres:5432` |
| Redis | `localhost:6379` | 컨테이너 내부에서는 `redis:6379` |
| MinIO S3 API | `http://localhost:9000` | 애플리케이션 객체 저장소 |
| MinIO 콘솔 | `http://localhost:9001` | 객체·버킷 확인 |

호스트의 기존 PostgreSQL이 `5432`를 사용하므로 Docker PostgreSQL은 충돌을 피하기 위해 `5434`로 공개한다. DBeaver는 Host `127.0.0.1`, Port `5434`, Database `abroad_to_korea`, Username `app`, Password는 `.env`의 `APP_DB_PASSWORD`로 접속한다.

## 첫 실행

새 환경에서만 예제 파일을 복사한다. 기존 `.env`에 TourAPI 키가 있다면 덮어쓰지 않는다.

```bash
cp .env.example .env
```

`.env`에서 최소한 아래 값을 서로 다른 긴 비밀번호로 변경한다.

```dotenv
POSTGRES_PASSWORD=change-me
APP_DB_PASSWORD=change-me
AIRFLOW_DB_PASSWORD=change-me
MLFLOW_DB_PASSWORD=change-me
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=change-me
```

구성을 검사하고 전체 서비스를 시작한다.

```bash
docker compose config --quiet
docker compose up --build -d
docker compose ps -a
```

최초 빌드는 Python·ML·Airflow 의존성과 MinIO 소스를 받아 컴파일하므로 오래 걸릴 수 있다. 공식 MinIO 컨테이너 이미지가 레지스트리에서 제공되지 않아 `infra/docker/Dockerfile.minio`가 고정 버전 소스를 직접 빌드한다. 이후 실행은 Docker 캐시를 사용한다.

`postgres`, `redis`, `mlflow`는 `healthy`, `api`, `minio`, `airflow-api-server`, `airflow-dag-processor`, `airflow-scheduler`는 `Up`이어야 한다. `migrate`, `mlflow-db-init`, `airflow-init`은 작업 성공 후 `Exited (0)`인 것이 정상이다.

## 데이터베이스 초기화와 변경

`infra/postgres/init/01-databases.sh`와 `02-mlflow-database.sh`는 빈 PostgreSQL 볼륨을 처음 만들 때 다음 DB와 계정을 생성한다.

- `abroad_to_korea`: 애플리케이션 DB, `app` 계정
- `airflow`: Airflow 메타 DB, `airflow` 계정
- `mlflow`: MLflow backend store, `mlflow` 계정

Alembic은 `infra/migrations/`의 변경 이력을 `abroad_to_korea`에 적용한다. 기존 볼륨에서는 `mlflow-db-init` 일회성 서비스가 MLflow DB와 계정만 멱등하게 준비한다. DB 이름이나 계정을 바꿀 때 운영 볼륨을 삭제하지 말고 SQL과 마이그레이션으로 변경한다.

현재 상태 확인:

```bash
docker compose exec postgres pg_isready -U postgres
docker compose run --rm migrate alembic -c infra/alembic.ini current
docker compose exec postgres psql -U postgres -d mlflow -c 'select count(*) from experiments;'
```

## MLflow 실험 추적

MLflow의 run·parameter·metric 메타데이터는 PostgreSQL의 `mlflow` DB에, `result.json` 같은 artifact는 MinIO의 `mlflow-artifacts` 버킷에 저장한다. 모델용 대용량 파일과 원천 데이터는 Git에 넣지 않는다.

현재 자동 기록 대상은 다음 세 가지다.

- `src/model/model_compare.py evaluate`: CLIP 모델별 Hit@5/10/20, MRR, 순위 통계
- `src/forecast/p1_spec.py kasi`: 월·일 혼잡도 기준 모델의 WAPE, medAPE
- `src/forecast/p1_holiday.py`: 분할·모델별 전체/연휴/명절/긴 연휴 WAPE

```bash
docker compose up --build -d postgres minio mlflow
curl --fail http://localhost:5000/health
.venv/bin/python src/forecast/p1_spec.py kasi
```

각 실험은 결과 JSON을 먼저 `data/interim/`에 저장한다. MLflow 접속 실패 때문에 긴 학습 결과까지 사라지지 않도록 추적 오류는 경고로 남기고 실행 결과는 유지한다. 재현성 확인을 위해 각 run에는 현재 Git commit을 tag로 기록한다.

## 인증

이메일 가입은 비밀번호를 Argon2id로 해시하고 즉시 활성 계정을 만든다. 이메일 인증 단계는 사용하지 않는다. 비밀번호 재설정 메일은 `email_outbox`에 작업을 만들고, `email-worker`가 작업을 잠근 뒤 Resend로 발송한다. Outbox UUID를 멱등성 키로 사용해 재시도 중 중복 발송을 방지한다.

세션·일회성 토큰은 원문 대신 해시를 PostgreSQL에 저장한다. Redis에는 5분 세션 캐시와 OAuth state가 들어가며, OAuth state는 Redis 장애 시 발급하지 않는다.

Google·Kakao는 같은 이메일이라는 이유만으로 기존 계정에 자동 연결하지 않는다. 로그인한 사용자가 `/api/auth/oauth/{provider}/start?mode=link`를 호출해야 연결된다. 운영 전 `.env`의 각 Client ID·Secret과 공급자 콘솔의 callback URL을 설정한다.

## 데이터 계층

- Staging: 호스트 `data/`의 수집 중간 파일·모델·행정 경계·임베딩
- Bronze: MinIO `bronze/tourapi/`의 체크섬 단위 원본 응답
- Image: MinIO `place-images/`의 공공누리 1·3유형 실제 사진
- User media: MinIO `uploads/`의 사용자 업로드
- Current: PostgreSQL의 `regions`, `places`, `place_images`, `festivals`, 지역 시계열
- Serving cache: Redis의 `query:*`, `auth:session:*`, `dataset_version`

Airflow 게시 작업은 원본 필수값을 먼저 검사하고 하나의 DB 트랜잭션에서 idempotent upsert한다. 실패한 실행은 기존 게시 데이터를 교체하지 않는다. 게시가 끝나면 Redis 검색 캐시를 무효화하고 데이터 버전을 갱신한다.

## Airflow 일정

| DAG | 일정 | 작업 |
|---|---|---|
| `tour_data_daily` | 매일 `00:15` | 추가 사진·음식 메뉴·향후 365일 축제 수집, 게시, 사진 캐시 |
| `tour_catalog_daily` | 매일 `01:45` | 관광지·레포츠·음식점 카탈로그 수집과 게시 |
| `user_media_cleanup_hourly` | 매시간 | 만료된 사용자 업로드 삭제 |
| `regional_metrics_monthly` | 매월 2일 `03:00` | 방문자 수·행정동 인구 수집 |

현재 `default_timezone`을 별도로 지정하지 않았으므로 cron 일정은 UTC 기준이다. 따라서 한국 시간으로는 각각 `09:15`, `10:45`, 매월 2일 `12:00`에 해당한다. 운영에서 한국 시간 기준 자정대로 실행하려면 Airflow timezone과 cron을 함께 조정한다. TourAPI 작업은 `tourapi` pool의 슬롯 1개로 직렬화하고, 일일 DAG는 3회 재시도한다.

새 DAG는 등록 즉시 활성화된다. 이 설정을 적용하기 전에 이미 등록되어 일시 중지된 DAG는 한 번만 `docker compose exec airflow-api-server airflow dags unpause '.*' --treat-dag-id-as-regex -y`로 활성화한다.

## 개인정보

사용자 업로드는 로그인 사용자가 `retain_photo=true`로 보관에 명시적으로 동의한 경우에만 MinIO와 `media_assets`에 저장된다(2026-10-08 결정). 동의하지 않은 사진은 분석만 하고 저장하지 않는다. 사진 삭제 요청은 `delete_after`를 현재 시각으로 바꾸고 다음 시간 단위 정리 작업에서 실제 객체를 삭제한다.

운영에서는 `COOKIE_SECURE=true`와 HTTPS를 사용한다. `.env`는 Git에 커밋하지 않는다.

## 운영 명령

```bash
docker compose ps -a
docker compose logs --tail=200 api
docker compose logs --tail=200 airflow-dag-processor
docker compose logs --tail=200 airflow-scheduler
docker compose restart api
docker compose stop
docker compose start
```

`docker compose down -v`는 PostgreSQL·Redis·MinIO 볼륨을 삭제하므로 운영 데이터가 있는 환경에서는 실행하지 않는다.

## 백업과 운영 전 필수 작업

- PostgreSQL 일일 백업과 실제 복원 훈련
- MinIO `minio-data` 버전 관리 또는 외부 복제
- MLflow `mlflow` DB와 `mlflow-artifacts` 버킷을 같은 복구 시점으로 백업
- Airflow DAG 실패 알림과 수집 지연 모니터링
- Resend 발신 도메인 SPF/DKIM/DMARC 인증과 운영용 발송 키 교체
- HTTPS·운영 도메인·OAuth callback URL 적용
- 기본 비밀번호 교체와 비밀 관리 도구 연결

백업 파일이 존재하는 것만으로는 충분하지 않다. 별도 환경에서 PostgreSQL과 MinIO를 함께 복원해 사용자·객체 참조가 일치하는지 확인해야 한다.
