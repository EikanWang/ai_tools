import smtplib
from email.message import EmailMessage
import mimetypes

def send_email_with_attachment(file_path, subject, from_email, to_email):
    with open(file_path, 'r') as f:
        file_data = f.read()

    with smtplib.SMTP('localhost') as s:
        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = from_email
        msg['To'] = to_email

        msg.set_content(file_data)

        ctype, encoding = mimetypes.guess_type(file_path)
        if ctype is None or encoding is not None:
            # No guess could be made, or the file is encoded (compressed), so
            # use a generic bag-of-bits type.
            ctype = 'application/octet-stream'

        maintype, subtype = ctype.split('/', 1)
        msg.add_attachment(file_data.encode('utf-8'), maintype=maintype, subtype=subtype, filename=file_path)

        # Send the message via our own SMTP server
        s.send_message(msg)