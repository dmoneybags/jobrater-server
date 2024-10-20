import datetime

class UserSubscription:
    def __init__(self, subscription_id: str, price_id: str, user_id: str, subscription_type: str, 
                 stripe_customer_id: str, stripe_subscription_id: str, status: str, created_at: datetime.datetime, 
                 current_period_end: datetime.datetime | None, canceled_at: datetime.datetime | None=None, is_active: bool=True):
        self.subscription_id: str = subscription_id
        self.price_id: str = price_id
        self.user_id: str = user_id
        self.subscription_type: str = subscription_type
        self.stripe_customer_id: str = stripe_customer_id
        self.stripe_subscription_id: str = stripe_subscription_id
        self.status: str = status
        self.created_at: datetime.datetime = created_at
        self.canceled_at: datetime.datetime | None = canceled_at
        self.is_active: bool = is_active
