# tests

```bash
.venv/bin/python -m pytest -q
```

| 파일 | 확인하는 것 |
|---|---|
| `test_api.py` | API 응답 모양, 입력 검증, 사진 동의 없이 저장 안 함, 평가 결과 파일 해시(연구 결과 보존) |
| `test_infrastructure.py` | 로그인 기본 함수, DB 스키마, 캐시 대체 동작, 수집 원본의 DB 게시 가능 여부 (실제 DB 없이 실행) |
| `test_email_worker.py`, `test_mlflow_tracking.py` | 메일 발송 작업, MLflow 기록 |

서버가 쓰는 데이터(`data/`)가 있어야 대부분 실행된다.
