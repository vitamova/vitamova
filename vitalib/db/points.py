import datetime

class Points:
    # Points are in the points table with columns user_id, points, task, timestamp
    def __init__(self, conn, user_id):
        self.conn = conn
        self.user_id = user_id
    def add(self, amount, task):
        with self.conn.cursor() as cur:
            query = """
                INSERT INTO points (user_id, points, task)
                VALUES (%s, %s, %s)
            """
            cur.execute(query, (self.user_id, amount, task))
        self.conn.commit()
        return {
            "status": "ok",
            "message": f"Added {amount} points for task '{task}'."
        }
    def this_week(self):
        # Start at Monday of this week 0:00:00:00 UTC
        now = datetime.datetime.utcnow()
        start_of_week = now - datetime.timedelta(days=now.weekday(), hours=now.hour, minutes=now.minute, seconds=now.second, microseconds=now.microsecond)
        with self.conn.cursor() as cur:
            query = """
                SELECT SUM(points) FROM points
                WHERE user_id = %s AND timestamp >= %s
            """
            cur.execute(query, (self.user_id, start_of_week))
            result = cur.fetchone()
        return result[0] if result else 0