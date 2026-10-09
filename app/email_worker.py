import asyncio
import html
from datetime import datetime, timezone

import httpx
from sqlalchemy import select

from .db import session_factory
from .models import EmailOutbox
from .settings import get_settings


def render_email(template: str, payload: dict) -> tuple[str, str, str]:
    token = html.escape(str(payload["token"]))
    if template == "reset_password":
        subject = "[Abroad to Korea] 비밀번호 재설정 토큰"
        heading = "비밀번호 재설정"
        message = "비밀번호를 재설정하려면 아래 토큰을 재설정 화면에 입력해 주세요."
    else:
        raise ValueError(f"지원하지 않는 이메일 템플릿입니다: {template}")

    text = f"{heading}\n\n{message}\n\n{token}\n\n이 토큰은 1시간 후 만료됩니다. 요청하지 않았다면 이 메일을 무시해 주세요."
    body = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  <title>{heading}</title>
</head>
<body style="margin:0; padding:0; background-color:#f5f5f5;">
  <table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation">
    <tr>
      <td align="center" style="padding-top:32px; padding-right:16px; padding-bottom:32px; padding-left:16px; background-color:#f5f5f5;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation" style="max-width:600px; background-color:#ffffff;">
          <tr>
            <td style="padding-top:32px; padding-right:32px; padding-bottom:32px; padding-left:32px; font-family:Arial, Helvetica, sans-serif;">
              <h1 style="margin-top:0; margin-right:0; margin-bottom:16px; margin-left:0; font-family:Arial, Helvetica, sans-serif; font-size:24px; line-height:32px; color:#111111;">{heading}</h1>
              <p style="margin-top:0; margin-right:0; margin-bottom:24px; margin-left:0; font-family:Arial, Helvetica, sans-serif; font-size:16px; line-height:24px; color:#333333;">{message}</p>
              <p style="margin-top:0; margin-right:0; margin-bottom:24px; margin-left:0; padding-top:16px; padding-right:16px; padding-bottom:16px; padding-left:16px; background-color:#f2f2f2; font-family:monospace; font-size:24px; line-height:32px; color:#111111; text-align:center; word-break:break-all;">{token}</p>
              <p style="margin-top:0; margin-right:0; margin-bottom:8px; margin-left:0; font-family:Arial, Helvetica, sans-serif; font-size:14px; line-height:21px; color:#666666;">이 토큰은 1시간 후 만료됩니다.</p>
              <p style="margin-top:0; margin-right:0; margin-bottom:0; margin-left:0; font-family:Arial, Helvetica, sans-serif; font-size:14px; line-height:21px; color:#666666;">요청하지 않았다면 이 메일을 무시해 주세요.</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
    return subject, text, body


async def send_email(row: EmailOutbox) -> str:
    settings = get_settings()
    if not settings.resend_api_key:
        raise RuntimeError("RESEND_API_KEY가 설정되지 않았습니다.")

    subject, text, body = render_email(row.template, row.payload)
    message = {
        "from": settings.resend_from_email,
        "to": [row.recipient],
        "subject": subject,
        "text": text,
        "html": body,
    }
    if settings.resend_reply_to:
        message["reply_to"] = settings.resend_reply_to

    headers = {
        "Authorization": f"Bearer {settings.resend_api_key}",
        "Idempotency-Key": f"email-outbox-{row.id}",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        for attempt in range(3):
            try:
                response = await client.post("https://api.resend.com/emails", headers=headers, json=message)
                if response.status_code not in {429} and response.status_code < 500:
                    response.raise_for_status()
                    return str(response.json()["id"])
            except httpx.HTTPStatusError:
                raise
            except httpx.HTTPError:
                if attempt == 2:
                    raise
            if attempt == 2:
                response.raise_for_status()
            await asyncio.sleep(2 ** attempt)
    raise RuntimeError("이메일 발송에 실패했습니다.")


async def process_next() -> bool:
    factory = session_factory()
    if factory is None:
        raise RuntimeError("DATABASE_URL이 설정되지 않았습니다.")
    async with factory() as db:
        row = await db.scalar(
            select(EmailOutbox)
            .where(EmailOutbox.sent_at.is_(None), EmailOutbox.failed_at.is_(None))
            .order_by(EmailOutbox.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if row is None:
            return False
        try:
            await send_email(row)
        except Exception as exc:
            row.failed_at = datetime.now(timezone.utc)
            row.error = str(exc)[:4000]
        else:
            row.sent_at = datetime.now(timezone.utc)
            row.error = None
        await db.commit()
        return True


async def run() -> None:
    settings = get_settings()
    if not settings.resend_api_key:
        raise RuntimeError("RESEND_API_KEY가 설정되지 않았습니다.")
    while True:
        if not await process_next():
            await asyncio.sleep(settings.email_worker_poll_seconds)


if __name__ == "__main__":
    asyncio.run(run())
