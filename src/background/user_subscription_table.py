import stripe
import json
import logging
import datetime
from database_functions import DatabaseFunctions, get_connection
from typing import Dict
from user_subscription import UserSubscription
from auth_logic import decode_user_from_token
from dateutil.relativedelta import relativedelta
from mysql.connector.errors import IntegrityError

class UserSubscriptionTable:
    def __get_add_subscription_query() -> str:
        return '''
            INSERT INTO UserSubscription ( UserId, Price, SubscriptionType, 
            StripeCustomerId, StripeSubscriptionId, 
            CreatedAt, CurrentPeriodEnd, 
            CanceledAt, IsActive
            ) VALUES (
                %s, %s, %s, 
                %s, %s, %s, 
                %s, %s, %s
            )
        '''
    def __get_cancel_subscription_query() -> str:
        return '''
            UPDATE UserSubscription SET IsActive=FALSE WHERE UserId = %s AND SubscriptionType = %s
        '''
    def __get_read_subscription_query() -> str:
        return '''
            SELECT * FROM UserSubscription WHERE UserID = %s
        '''
    def __get_read_subscription_query_by_sub_stripe_id() -> str:
        return '''
            SELECT * FROM UserSubscription WHERE StripeSubscriptionId = %s
        '''
    def __get_update_subscription_query() -> str:
        return '''
            UPDATE UserSubscription SET Price=%s, SubscriptionType=%s, StripeCustomerId=%s, StripeSubscriptionId=%s,
            CreatedAt=%s, CurrentPeriodEnd=%s, CanceledAt=%s, IsActive=%s WHERE UserId=%s
        '''
    def __add_subscription(user_subscription: UserSubscription) -> UserSubscription:
        logging.info("Adding subscription")
        with get_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                query = UserSubscriptionTable.__get_add_subscription_query()
                values = (str(user_subscription.user_id), user_subscription.subscription_object.price, user_subscription.subscription_object.subscription_type,
                          user_subscription.stripe_customer_id, user_subscription.stripe_subscription_id, user_subscription.created_at,
                          user_subscription.current_period_end, user_subscription.canceled_at, user_subscription.is_active)
                cursor.execute(query, values)
                logging.info("Added subscription")
                logging.debug(json.dumps(user_subscription.to_json(), indent=2))
                conn.commit()
                return user_subscription
    def read_subscription(userId: str) -> UserSubscription | None:
        userId = str(userId) #when I forget to convert it to uuid
        logging.info("Reading subscription")
        with get_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                query = UserSubscriptionTable.__get_read_subscription_query()
                cursor.execute(query, (userId,))
                query_result = cursor.fetchone()
                if not query_result:
                    return None
                return UserSubscription.generate_from_sql_row(query_result)
    def read_subscription_by_stripe_sub_id(stripe_subscription_id: str) -> UserSubscription | None:
        logging.info("Reading subscription")
        with get_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                query = UserSubscriptionTable.__get_read_subscription_query_by_sub_stripe_id()
                cursor.execute(query, (stripe_subscription_id,))
                query_result = cursor.fetchone()
                if not query_result:
                    return None
                return UserSubscription.generate_from_sql_row(query_result)
    def __update_subscription(user_subscription: UserSubscription) -> UserSubscription:
        logging.info("Updating subscription")
        with get_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                query = UserSubscriptionTable.__get_update_subscription_query()
                values = (user_subscription.subscription_object.price, user_subscription.subscription_object.subscription_type,
                          user_subscription.stripe_customer_id, user_subscription.stripe_subscription_id, user_subscription.created_at,
                          user_subscription.current_period_end, user_subscription.canceled_at, user_subscription.is_active,
                          str(user_subscription.user_id))
                cursor.execute(query, values)
                logging.info("Updated subscription")
                conn.commit()
                return user_subscription
    def add_or_update_subscription(user_subscription: UserSubscription) -> UserSubscription:
        logging.info("Adding or updating subscription")
        reread_subscription: UserSubscription | None = UserSubscriptionTable.read_subscription(user_subscription.user_id)
        if reread_subscription:
            if reread_subscription.subscription_object.subscription_type == user_subscription.subscription_object.subscription_type and reread_subscription.valid():
                logging.error("User is already subscribed! ensure this is a race condition")
                raise ValueError("User is already subscribed! ensure this is a race condition")
            return UserSubscriptionTable.__update_subscription(user_subscription)
        return UserSubscriptionTable.__add_subscription(user_subscription)
    def fulfill_checkout(session_id: str):
        session = stripe.checkout.Session.retrieve(
            session_id,
            expand=['line_items'],
        )
        if session.payment_status != 'unpaid':
            user_subscription: UserSubscription = UserSubscription.generate_from_session(session)
            return UserSubscriptionTable.add_or_update_subscription(user_subscription)
    def renew(subscription_id: str) -> UserSubscription:
        try:
            user_subscription: UserSubscription = UserSubscriptionTable.read_subscription_by_stripe_sub_id(subscription_id)
            stripe_subscription: stripe.Subscription = stripe.Subscription.retrieve(subscription_id)
            user_subscription.current_period_end = datetime.datetime.fromtimestamp(stripe_subscription.current_period_end)
            return UserSubscriptionTable.__update_subscription(user_subscription)

        except stripe.error.StripeError as e:
            print(f"Stripe error occurred: {e.user_message}")
            raise
        except Exception as e:
            print(f"An error occurred: {e}")
            raise
    def cancel(subscription_id: str) -> UserSubscription:
        user_subscription: UserSubscription = UserSubscriptionTable.read_subscription_by_stripe_sub_id(subscription_id)
        user_subscription.is_active = False
        return UserSubscriptionTable.__update_subscription(user_subscription)