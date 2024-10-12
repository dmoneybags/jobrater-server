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
    def send_confirmation_email(receiver_email, confirmation_code):
        subject = "ApplicantIQ Email Confirmation"
        body_text = f'''
        Thank you for registering with ApplicantIQ! Here is your 6 digit confirmation code:

        {confirmation_code}

        Return to the browser extension to finish the onboarding.
        '''
        Mailing.send_email(subject, body_text, receiver_email)
