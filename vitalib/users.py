import vitalib
import datetime
import stripe
import os

stripe.api_key = os.environ.get("STRIPE_PRIVATE_KEY")

class User:
    class Registration:
        def __init__(self, user_id, conn):
            self.user_id = user_id
            self.conn = conn

        def is_valid(self):
            user_info = vitalib.Database.UserInfo.Get(self.conn, self.user_id).data()
            return user_info is not None
    
    class Subscription:
        def __init__(self, user_id, email, conn):
            self.user_id = user_id
            self.email = email
            self.conn = conn

        def is_active(self):
            subscription_info = vitalib.Database.UserInfo.Get(
                self.conn,
                self.user_id
            ).data(
                "subscribed",
                "subscription_expiration",
                "stripe_customer_id"
            )

            today = datetime.datetime.now(datetime.timezone.utc).date()

            if (
                subscription_info
                and subscription_info.get("subscribed")
                and subscription_info.get("subscription_expiration")
                and subscription_info.get("subscription_expiration") > today
            ):
                return True

            user_email = self.email

            if not user_email:
                return False

            stripe_status = self.check_stripe()

            vitalib.Database.UserInfo.Update(
                self.conn,
                self.user_id
            ).data(
                subscribed=stripe_status["subscribed"],
                subscription_expiration=stripe_status["subscription_expiration"],
                stripe_customer_id=(
                    stripe_status["stripe_customer_id"]
                    or subscription_info.get("stripe_customer_id")
                ),
            )

            return bool(
                stripe_status["subscribed"]
                and stripe_status["subscription_expiration"]
                and stripe_status["subscription_expiration"] > today
            )

        def check_stripe(self):
            result = {
                "subscribed": False,
                "subscription_expiration": None,
                "stripe_customer_id": None,
            }

            user_email = self.email

            customers = stripe.Customer.list(email=user_email, limit=10).data

            for customer in customers:
                customer_id = customer.get("id")

                if not customer_id:
                    continue

                subscriptions = stripe.Subscription.list(
                    customer=customer_id,
                    status="all",
                    limit=100,
                ).data

                for sub in subscriptions:
                    if sub.get("status") not in ["active", "trialing"]:
                        continue

                    for item in sub.get("items", {}).get("data", []):
                        price_id = item.get("price", {}).get("id")

                        if price_id not in VITAMOVA_PRICE_MAP:
                            continue

                        current_period_end = (
                            sub.get("current_period_end")
                            or item.get("current_period_end")
                        )

                        subscription_expiration = None

                        if current_period_end:
                            subscription_expiration = datetime.date.fromtimestamp(
                                current_period_end
                            )

                        return {
                            "subscribed": True,
                            "subscription_expiration": subscription_expiration,
                            "stripe_customer_id": customer_id,
                        }

            return result
            today = datetime.datetime.now(datetime.timezone.utc).date()

            customers = stripe.Customer.list(email=user_email, limit=10).data

            for customer in customers:
                customer_id = customer.get("id")

                if not customer_id:
                    continue

                subscriptions = stripe.Subscription.list(
                    customer=customer_id,
                    status="all",
                    limit=100,
                ).data

                for sub in subscriptions:
                    if sub.get("status") not in ["active", "trialing"]:
                        continue

                    for item in sub.get("items", {}).get("data", []):
                        price_id = item.get("price", {}).get("id")

                        if price_id not in VITAMOVA_PRICE_MAP:
                            continue

                        current_period_end = (
                            sub.get("current_period_end")
                            or item.get("current_period_end")
                        )

                        subscription_expiration = None

                        if current_period_end:
                            subscription_expiration = datetime.date.fromtimestamp(
                                current_period_end
                            )

                        vitalib.Database.UserInfo.Update(
                            self.conn,
                            self.user_id
                        ).data(
                            subscribed=True,
                            subscription_expiration=subscription_expiration,
                            stripe_customer_id=customer_id,
                        )

                        return bool(
                            subscription_expiration
                            and subscription_expiration > today
                        )

            vitalib.Database.UserInfo.Update(
                self.conn,
                self.user_id
            ).data(
                subscribed=False,
                subscription_expiration=None,
            )

            return False