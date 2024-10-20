import os

class Subscription:
    PRO_SUBSCRIPTION_PRICE = 999
    PRO_SUBSCRIPTION_BASE_PRICE_TEST_ID = "price_1QBsnwKfLZqN2X3WBnykVH85"
    PRO_SUBSCRIPTION_BASE_PRICE_ID = "price_1QBmFMKfLZqN2X3WL0H7dHm4" if os.environ["SERVER_ENVIRONMENT"] == "production" else PRO_SUBSCRIPTION_BASE_PRICE_TEST_ID
    PRO_SUBCRIPTION_TEST_ID = "prod_R40ppWMFQ1pXtu"
    PRO_SUBSCRIPTION_ID = "prod_R3u3Q6oY9Z7PsZ" if os.environ["SERVER_ENVIRONMENT"] == "production" else PRO_SUBCRIPTION_TEST_ID

    def get_price_code(product_id: str, discount_code: str):
        #no discount codes as of now
        if (product_id == Subscription.PRO_SUBSCRIPTION_ID):
            return Subscription.PRO_SUBSCRIPTION_BASE_PRICE_ID if os.environ["SERVER_ENVIRONMENT"] == "production" else Subscription.PRO_SUBSCRIPTION_BASE_PRICE_TEST_ID
        else:
            raise ValueError(f"Invalid product_id or discount_code: {product_id} {discount_code}.")

    def __init__(self, subscription_type: str, price_override: int = None, discount_code: str = None) -> None:
        self.subscription_type = subscription_type
        self.discount_code = discount_code
        if subscription_type == "pro":
            self.price = price_override or Subscription.PRO_SUBSCRIPTION_PRICE
            self.product_id = Subscription.PRO_SUBSCRIPTION_ID
            self.price_id = Subscription.PRO_SUBSCRIPTION_BASE_PRICE_ID
        else:
            raise ValueError(f"Invalid subscription_type: {subscription_type}.")
    def to_line_item(self):
        return {
            'price': self.price_id,
            'quantity': 1
        }
    
    