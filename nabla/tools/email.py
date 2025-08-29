import os

USER_EMAIL = os.environ.get("USER_EMAIL", "alban.andrieu@gmail.com")
IMAP_USER = os.environ.get("IMAP_USER", USER_EMAIL)
IMAP_PASSWORD = os.environ.get("IMAP_PASSWORD", "your_app_password")
IMAP_SERVER = os.environ.get("IMAP_SERVER", "imap.gmail.com")
IMAP_FOLDER = os.environ.get("IMAP_FOLDER", "inbox")

# mail = imaplib.IMAP4_SSL(IMAP_SERVER)
# mail.login(IMAP_USER, IMAP_PASSWORD)
# mail.select(IMAP_FOLDER)
# status, messages = mail.search(None, '(UNSEEN SUBJECT "newsletter")')
# for num in messages[0].split():
#     mail.store(num, "+FLAGS", "\\Deleted")
# mail.expunge()
# mail.logout()
