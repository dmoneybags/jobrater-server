import boto3
from botocore.exceptions import ClientError
import random

class Mailing:
    domain = "applicantiq.org"
    info_email_address = "info@" + domain
    region = "us-west-1"
    def send_email(subject, body_text, receiver_email, sender_email=info_email_address):
        ses_client = boto3.client('ses', region_name=Mailing.region)

        try:
            response = ses_client.send_email(
                Source=sender_email,
                Destination={
                    'ToAddresses': [receiver_email],
                },
                Message={
                    'Subject': {
                        'Data': subject,
                    },
                    'Body': {
                        'Text': {
                            'Data': body_text,
                        },
                    },
                }
            )
            print("Email sent! Message ID:", response['MessageId'])
            return response['MessageId']
        except ClientError as e:
            print("Error sending email:", e.response['Error']['Message'])
            return None
    def send_confirmation_email(receiver_email, confirmation_code, forgot_password=False):
        subject = "ApplicantIQ Email Confirmation"
        body_text: str
        if forgot_password:
            body_text =f'''Here is your 6 digit confirmation code: {confirmation_code}'''
        else:
            body_text = f'''Thank you for registering with ApplicantIQ! Here is your 6 digit confirmation code: {confirmation_code}'''
        Mailing.send_email(subject, body_text, receiver_email)
