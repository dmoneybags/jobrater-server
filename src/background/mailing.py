import requests
import os
import random
import logging

class Mailing:
    domain = "applicantiq.org"
    info_email_address = "info@" + domain
    mailgun_url = "https://api.mailgun.net/v3/applicantiq.org/messages"
    def send_email(subject, body_text, receiver_email, sender_email=info_email_address):
        response = requests.post(
  		Mailing.mailgun_url,
  		auth=("api", os.environ.get("MAILGUN_API_KEY")),
  		data={"from": f"ApplicantIQ <{sender_email}>",
  			"to": [receiver_email],
  			"subject": subject,
  			"text": body_text})
        logging.info("Sent request to send email")
        logging.info("Status Code:")
        logging.info(response.status_code)  # HTTP status code
        logging.info("Response Text:")
        logging.info(response.text)
        logging.info(os.environ.get("MAILGUN_API_KEY"))   
    def send_confirmation_email(receiver_email, confirmation_code, forgot_password=False):
        subject = "ApplicantIQ Email Confirmation"
        body_text: str
        if forgot_password:
            body_text =f'''Here is your 6 digit confirmation code: {confirmation_code}'''
        else:
            body_text = f'''Thank you for registering with ApplicantIQ! Here is your 6 digit confirmation code: {confirmation_code}'''
        Mailing.send_email(subject, body_text, receiver_email)
