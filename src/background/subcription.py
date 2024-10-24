import os
from typing import Dict

class Subscription:
    PRO_SUBSCRIPTION_PRICE = 999
    PRO_SUBSCRIPTION_DISCOUNTED_PRICE = 699
    PRO_SUBSCRIPTION_BASE_PRICE_TEST_ID = "price_1QBsnwKfLZqN2X3WBnykVH85"
    PRO_SUBSCRIPTION_DISCOUNTED_PRICE_TEST_ID = "price_1QDXyVKfLZqN2X3WScUNYTel"
    PRO_SUBSCRIPTION_DISCOUNTED_PRICE_ID = "" if os.environ["STRIPE_ENVIRONMENT"] == "production" else PRO_SUBSCRIPTION_DISCOUNTED_PRICE_TEST_ID
    PRO_SUBSCRIPTION_BASE_PRICE_ID = "price_1QBmFMKfLZqN2X3WL0H7dHm4" if os.environ["STRIPE_ENVIRONMENT"] == "production" else PRO_SUBSCRIPTION_BASE_PRICE_TEST_ID
    PRO_SUBCRIPTION_TEST_ID = "prod_R40ppWMFQ1pXtu"
    PRO_SUBSCRIPTION_ID = "prod_R3u3Q6oY9Z7PsZ" if os.environ["STRIPE_ENVIRONMENT"] == "production" else PRO_SUBCRIPTION_TEST_ID

    EARLY_SIGNUP_CODE = "early"

    def __init__(self, subscription_type: str, price: int = None, discount_code: str = None) -> None:
        self.subscription_type = subscription_type
        self.discount_code = discount_code
        if subscription_type == "pro":
            self.price = price or Subscription.PRO_SUBSCRIPTION_PRICE
            self.product_id = Subscription.PRO_SUBSCRIPTION_ID
            self.price_id = Subscription.PRO_SUBSCRIPTION_DISCOUNTED_PRICE_TEST_ID if price == Subscription.PRO_SUBSCRIPTION_DISCOUNTED_PRICE else Subscription.PRO_SUBSCRIPTION_BASE_PRICE_ID
        else:
            raise ValueError(f"Invalid subscription_type: {subscription_type}.")
    def to_json(self):
        return {
            "subscriptionType": self.subscription_type,
            "discountCode": self.discount_code,
            "price": self.price,
            "productId": self.product_id,
            "priceId": self.price_id
        }

    @classmethod
    def generate_from_json(cls, json_object: Dict):
        subscription_type = json_object.get("subscriptionType")
        discount_code = json_object.get("discountCode")
        price = json_object.get("price")
        product_id = json_object.get("productId")
        price_id = json_object.get("priceId")
        
        if not subscription_type:
            raise ValueError("Missing subscriptionType in JSON data.")
        
        subscription = cls(
            subscription_type=subscription_type,
            discount_code=discount_code,
        )
        
        # If price, product_id, and price_id are provided in JSON, assign them
        subscription.price = price
        subscription.product_id = product_id
        subscription.price_id = price_id

        return subscription
    
    def get_price_code(product_id: str, discount_code: str):
        #no discount codes as of now
        if (product_id == Subscription.PRO_SUBSCRIPTION_ID):
            return Subscription.PRO_SUBSCRIPTION_BASE_PRICE_ID if os.environ["SERVER_ENVIRONMENT"] == "production" else Subscription.PRO_SUBSCRIPTION_BASE_PRICE_TEST_ID
        else:
            raise ValueError(f"Invalid product_id or discount_code: {product_id} {discount_code}.")
        
    def to_line_item(self):
        return {
            'price': self.price_id,
            'quantity': 1
        }
    
    