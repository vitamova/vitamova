import vitalib
import datetime

class User:
    class Registration:
        def __init__(self, user_id, conn):
            self.user_id = user_id
            self.conn = conn

        def is_valid(self):
            user_info = vitalib.Database.UserInfo.Get(self.conn, self.user_id).data()
            return user_info is not None
    
    class Subscription:
        def __init__(self, user_id, conn):
            self.user_id = user_id
            self.conn = conn

        def is_active(self):
            subscription_info = vitalib.Database.UserInfo.Get(self.conn, self.user_id).data("subscribed", "subscription_expiration","stripe_customer_id")
            # If subscibed is True and subscription_expiration is in the future, return True
            if subscription_info and subscription_info.get("subscribed") and subscription_info.get("suscription_expiration") > datetime.datetime.now(datetime.timezone.utc):
                return True