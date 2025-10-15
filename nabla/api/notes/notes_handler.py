from nabla.utils.email import EmailSchema, send_in_background
from nabla.utils.logger import logger


# notes_handler.py
async def handle_note(note):
    note_type = note["type"]
    prompt = note["prompt"]

    if note_type == "email":
        await send_email(prompt)
    elif note_type == "note":
        logger.info(f"Note: {prompt}")
    elif note_type == "transform":
        await transform_data(prompt)
    else:
        logger.warning(f"Unknown note type: {note_type}")


async def send_email(prompt):
    logger.info(f"Sending email to {prompt['to']} with subject {prompt['subject']}")

    email = EmailSchema(email=prompt["to"])

    send_in_background(email)
    # await router.post("/email", email=EmailSchema(email=prompt['to']))


async def transform_data(prompt):
    logger.info("Running data transformation note...")
