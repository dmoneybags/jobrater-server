import datetime
import stripe
import json
from auth_logic import decode_user_from_token
from user import User
from dateutil.relativedelta import relativedelta
from subcription import Subscription
from mysql.connector.types import RowType, RowItemType
from typing import Dict

class UserSubscription:
    def __init__(self, subscription_id: int, user_id: str, subscription_type: str, price: int,
                 stripe_customer_id: str, stripe_subscription_id: str, created_at: datetime.datetime, 
                 current_period_end: datetime.datetime | None, canceled_at: datetime.datetime | None=None, is_active: bool=True):
        self.subscription_id: str = subscription_id
        self.user_id: str = user_id
        self.subscription_object: Subscription = Subscription(subscription_type, price)
        self.stripe_customer_id: str = stripe_customer_id
        self.stripe_subscription_id: str = stripe_subscription_id
        self.created_at: datetime.datetime = created_at
        self.current_period_end: datetime.datetime = current_period_end
        self.canceled_at: datetime.datetime | None = canceled_at
        self.is_active: bool = is_active
    def valid(self):
        return datetime.datetime.now() < self.current_period_end
    def to_json(self):
        return {
            "subscriptionId": self.subscription_id,
            "userId": str(self.user_id),
            "subscriptionObject": self.subscription_object.to_json(),
            "stripeCustomerId": self.stripe_customer_id,
            "stripeSubscriptionId": self.stripe_subscription_id,
            "createdAt": self.created_at.timestamp(),
            "currentPeriodEnd": self.current_period_end.timestamp(),
            "canceledAt": self.canceled_at.timestamp() if self.canceled_at else None,
            "isActive": self.is_active
        }
    @classmethod
    def generate_from_json(cls, json_object: Dict):
        subscription: Subscription = Subscription.generate_from_json(json_object["subscriptionObject"])
        return cls(json_object["subscriptionId"],
                   json_object["userId"],
                   subscription.subscription_type,
                   subscription.price,
                   json_object["stripeCustomerId"],
                   json_object["stripeSubscriptionId"],
                   datetime.datetime.fromtimestamp(json_object["createdAt"]),
                   datetime.datetime.fromtimestamp(json_object["currentPeriodEnd"]),
                   canceled_at=datetime.datetime.fromtimestamp(json_object["canceledAt"]) if json_object["canceledAt"] else None,
                   is_active=json_object["isActive"]
                   )
    @classmethod
    def generate_from_session(cls, session: stripe.checkout.Session) -> 'UserSubscription':
        user: User = decode_user_from_token(session.metadata.get("token", None))
        subscription_type: str = session.metadata.get("subscriptionType", None)
        price: int = session.amount_subtotal
        user_id: str = str(user.user_id)
        stripe_customer_id: str = session.customer
        stripe_subscription_id: str = session.subscription
        stripe_subscription: stripe.Subscription = stripe.Subscription.retrieve(stripe_subscription_id)
        created_at: datetime.datetime = datetime.datetime.fromtimestamp(session.created)
        current_period_end: datetime.datetime = datetime.datetime.fromtimestamp(stripe_subscription.current_period_end)
        canceled_at: datetime.datetime | None = None
        is_active: bool = True
        return cls(-1, user_id, subscription_type, price, stripe_customer_id, stripe_subscription_id, created_at,
                   current_period_end, canceled_at=canceled_at, is_active=is_active)
    @classmethod
    def generate_from_sql_row(cls, sql_query_row: (Dict[str, RowItemType])):
        subscription_id: int = sql_query_row["SubscriptionId"]
        subscription_type: str = sql_query_row["SubscriptionType"]
        price: int = sql_query_row["Price"]
        user_id: str = sql_query_row["UserId"]
        stripe_customer_id: str = sql_query_row["StripeCustomerId"]
        stripe_subscription_id: str = sql_query_row["StripeSubscriptionId"]
        created_at: datetime.datetime = sql_query_row["CreatedAt"]
        current_period_end: datetime.datetime = sql_query_row["CurrentPeriodEnd"]
        canceled_at: datetime.datetime | None = sql_query_row["CanceledAt"]
        is_active: bool = bool(sql_query_row["IsActive"])
        return cls(subscription_id, user_id, subscription_type, price, stripe_customer_id, stripe_subscription_id, created_at,
                   current_period_end, canceled_at=canceled_at, is_active=is_active)
    