"""Delete records past their retention period. 기한은 web/public/privacy.html (개인정보처리방침)에 적은 값과 같아야 한다."""

import os

import psycopg

SEARCH_LOG_DAYS = 90   # 검색 기록
EMAIL_OUTBOX_DAYS = 30  # 보내거나 실패한 메일 발송 기록 (받는 사람 이메일이 들어 있다)


def main() -> None:
    url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(url) as conn:
        searches = conn.execute("DELETE FROM search_logs WHERE created_at < now() - make_interval(days => %s)",
                                (SEARCH_LOG_DAYS,)).rowcount
        mails = conn.execute("DELETE FROM email_outbox WHERE (sent_at IS NOT NULL OR failed_at IS NOT NULL)"
                             " AND created_at < now() - make_interval(days => %s)", (EMAIL_OUTBOX_DAYS,)).rowcount
        conn.commit()
    print(f"{SEARCH_LOG_DAYS}일 지난 검색 기록 {searches}건, {EMAIL_OUTBOX_DAYS}일 지난 메일 발송 기록 {mails}건 삭제", flush=True)


if __name__ == "__main__":
    main()
