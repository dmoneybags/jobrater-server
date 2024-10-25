from functools import wraps
import os
from typing import Callable, Tuple, Dict
from user import User
import logging
from resume_table import ResumeTable
from user_subscription import UserSubscription
from user_subscription_table import UserSubscriptionTable
from user_free_data_table import UserFreeDataTable
from errors import NoFreeRatingsLeft
from auth_logic import decode_user_from_token
from flask import Flask, request, jsonify, abort, Response

class PaymentDecorators:
    #flag for if we're actually requiring payment, for beta testing we leave this off
    REQUIRING_PAYMENT = os.environ.get("REQUIRE_PAYMENT", 1)
    if not REQUIRING_PAYMENT:
        logging.critical('''
    #
    #   CRITICAL WARNING: DO NOT REGARD PLEASE READ AND BE PREPARED TO EMERGENCY SHUTDOWN SERVER
    #
    #   REQUIRING PAYMENT IS TURNED OFF. THIS IS ONLY FOR BETA TESTING AND SHOULD NEVER BE USED IN PRODUCTION
    #
    ''')
    '''
    Symbolic class to hold decorators for routes that require payment.

    These decorators check that the user is subscribed/derement free tier resume ratings etc.

    If the user does not have the right! to DO! what they want to do!!!! THEN!!!!! WE!!!! RETURN!!!!

    A 402!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

    put these decorators after the token required decorator, we will not check for tokens and if they are not present
    these WILL KEYERROR

    EX:

    @pro_subscription_required  # This is applied second
    @token_required             # This is applied first, but runs first
    '''
    #can edit logic more if needed once premium comes along
    def pro_subscription_required(f: Callable) -> Callable:
        @wraps(f)
        def decorated(*args, **kwargs) -> Tuple[Response, int]:
            if PaymentDecorators.REQUIRING_PAYMENT:
                token: str = request.headers['Authorization']
                user : User | None = decode_user_from_token(token)
                user_subscription: UserSubscription = UserSubscriptionTable.read_subscription(user.user_id)
                if not user_subscription or not user_subscription.valid():
                    return jsonify({'message': 'Pro Subscription required'}), 402
            return f(*args, **kwargs)
        return decorated
    def check_subscription_for_resume_upload(f: Callable) -> Callable:
        @wraps(f)
        def decorated(*args, **kwargs) -> Tuple[Response, int]:
            if PaymentDecorators.REQUIRING_PAYMENT:
                token: str = request.headers['Authorization']
                user : User | None = decode_user_from_token(token)
                user_subscription: UserSubscription = UserSubscriptionTable.read_subscription(user.user_id)
                if not user_subscription or not user_subscription.valid():
                    if len(ResumeTable.read_user_resumes(user.user_id)):
                        return jsonify({'message': 'Pro Subscription required'}), 402
            return f(*args, **kwargs)
        return decorated
    def check_subscription_for_resume_rating(f: Callable) -> Callable:
        @wraps(f)
        def decorated(*args, **kwargs) -> Tuple[Response, int]:
            if PaymentDecorators.REQUIRING_PAYMENT:
                token: str = request.headers['Authorization']
                user : User | None = decode_user_from_token(token)
                user_subscription: UserSubscription = UserSubscriptionTable.read_subscription(user.user_id)
                if not user_subscription or not user_subscription.valid():
                    try:
                        UserFreeDataTable.use_free_resume_rating(user.user_id)
                    except NoFreeRatingsLeft:
                        return jsonify({'message': 'Pro Subscription required'}), 402
            return f(*args, **kwargs)
        return decorated
    