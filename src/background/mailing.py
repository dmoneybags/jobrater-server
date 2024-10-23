import requests
import os
import logging
from jinja2 import Template

class Mailing:
    domain = "applicantiq.org"
    info_email_address = "info@" + domain
    mailgun_url = "https://api.mailgun.net/v3/applicantiq.org/messages"
    def get_html_from_file(template_name: str) -> str:
        file_path: str = os.path.join(os.getcwd(), "src", "background", "email_templates", template_name + ".html")
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                html_content = file.read()
            return html_content
        except FileNotFoundError:
            return "File not found."
        except Exception as e:
            return f"An error occurred: {e}"
    def render_template(html_template: str, variables: dict) -> str:
        template = Template(html_template)
        return template.render(variables)
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
    def send_html_email(subject, body_html, receiver_email, sender_email=info_email_address, variables=None):
        if variables:
            body_html = Mailing.render_template(body_html, variables)
        response = requests.post(
  		Mailing.mailgun_url,
  		auth=("api", os.environ.get("MAILGUN_API_KEY")),
  		data={"from": f"ApplicantIQ <{sender_email}>",
  			"to": [receiver_email],
  			"subject": subject,
  			"html": body_html})
        logging.info("Sent request to send email")
        logging.info("Status Code:")
        logging.info(response.status_code)  # HTTP status code
        logging.info("Response Text:")
        logging.info(response.text)
    def send_confirmation_email(receiver_email, confirmation_code, forgot_password=False):
        subject = "ApplicantIQ Email Confirmation"
        body_text: str
        if forgot_password:
            body_text =f'''Here is your 6 digit confirmation code: {confirmation_code}'''
        else:
            body_text = f'''Thank you for registering with ApplicantIQ! Here is your 6 digit confirmation code: {confirmation_code}'''
        Mailing.send_email(subject, body_text, receiver_email)

