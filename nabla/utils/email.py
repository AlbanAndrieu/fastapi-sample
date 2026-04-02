import os
from typing import List

from fastapi import APIRouter
from fastapi.background import BackgroundTasks

# from fastapi_mail import (
#     ConnectionConfig,
#     FastMail,
#     MessageSchema,
#     MessageType,
#     MultipartSubtypeEnum,
# )
from pydantic import BaseModel, EmailStr
from starlette.responses import JSONResponse


class EmailSchema(BaseModel):
    email: List[EmailStr]


MAIL_INBOX_FOLDER = os.environ.get("MAIL_INBOX_FOLDER", "inbox")

MAIL_TO = os.environ.get("MAIL_TO", "alban.andrieu@free.fr")
MAIL_FROM = os.environ.get("MAIL_FROM", "alban.andrieu@gmail.com")

# conf = ConnectionConfig(
#     MAIL_USERNAME=os.environ.get("MAIL_USERNAME", "username"),
#     MAIL_PASSWORD=os.environ.get("MAIL_PASSWORD", "password"),
#     MAIL_FROM=MAIL_FROM,
#     MAIL_PORT=int(os.environ.get("MAIL_PORT", "587")),
#     MAIL_SERVER=os.environ.get("MAIL_SERVER", "imap.gmail.com"),
#     MAIL_FROM_NAME=os.environ.get("MAIL_FROM_NAME", "Alban Andrieu"),
#     MAIL_STARTTLS=True,
#     MAIL_SSL_TLS=False,
#     USE_CREDENTIALS=True,
#     VALIDATE_CERTS=True,
# )


router = APIRouter()

# fm = FastMail(conf)
# message = MessageSchema(subject="Test Email", recipients=[MAIL_TO], body="Hello FastAPI")

# await fm.send_message(message)

# mail = imaplib.IMAP4_SSL(MAIL_SERVER)
# mail.login(MAIL_USERNAME, MAIL_PASSWORD)
# mail.select(MAIL_INBOX_FOLDER)
# status, messages = mail.search(None, '(UNSEEN SUBJECT "newsletter")')
# for num in messages[0].split():
#     mail.store(num, "+FLAGS", "\\Deleted")
# mail.expunge()
# mail.logout()


@router.post("/email")
async def simple_send(email: EmailSchema) -> JSONResponse:
    # message = MessageSchema(
    #     subject="Fastapi-Mail module",
    #     recipients=email.dict().get("email"),
    #     body="""<p>Hi this test mail, thanks for using Fastapi-mail</p>""",
    #     subtype=MessageType.html,
    # )

    # fm = FastMail(conf)
    # await fm.send_message(message)
    return JSONResponse(status_code=200, content={"message": "email has been sent"})


@router.post("/emailbackground")
async def send_in_background(
    background_tasks: BackgroundTasks,
    email: EmailSchema,
) -> JSONResponse:
    # message = MessageSchema(
    #     subject="Fastapi mail module",
    #     recipients=email.dict().get("email"),
    #     body="Simple background task",
    #     template_body="<b>This is a test email</b>",
    #     subtype=MessageType.plain,
    #     alternative_body="This is a test email",
    #     multipart_subtype=MultipartSubtypeEnum.alternative,
    # )

    # fm = FastMail(conf)

    # background_tasks.add_task(fm.send_message, message)

    return JSONResponse(status_code=200, content={"message": "email has been sent"})
