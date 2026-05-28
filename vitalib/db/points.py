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