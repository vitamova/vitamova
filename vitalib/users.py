import vitalib

class User:
    class Registration:
        def __init__(self, user_id, conn):
            self.user_id = user_id
            self.conn = conn

        def is_valid(self):
            user_info = vitalib.UserInfo.Get(self.conn, self.user_id).data()
            return user_info is not None
    
    class Subscription:
        pass