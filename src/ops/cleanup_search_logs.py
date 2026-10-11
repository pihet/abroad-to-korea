"""Delete search logs older than the retention period (개인정보처리방침에 적은 기한과 같아야 한다)."""

import os

import psycopg

RETENTION_DAYS = 90


def main() -> None:
    url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(url) as conn:
        n = conn.execute("DELETE FROM search_logs WHERE created_at < now() - make_interval(days => %s)",
                         (RETENTION_DAYS,)).rowcount
        conn.commit()
    print(f"{RETENTION_DAYS}일 지난 검색 기록 {n}건 삭제", flush=True)


if __name__ == "__main__":
    main()
