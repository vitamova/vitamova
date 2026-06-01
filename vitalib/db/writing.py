import datetime

class Writing:
    class Prompt:
        def __init__(self, conn, user_id, language):
            self.conn = conn
            self.user_id = user_id
            self.language = language
        def get(self):
            # Get a random writing prompt from the database for the specified language
            # Database name is writing_prompts
            # Columns are: id, language, title, text
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, title, text
                    FROM writing_prompts
                    WHERE language = %s
                    ORDER BY RANDOM()
                    LIMIT 1
                """, (self.language,))
                row = cursor.fetchone()
                if row:
                    return {
                        "id": row[0],
                        "title": row[1],
                        "text": row[2]
                    }
                else:
                    return None
    class Submission:
        def __init__(self, conn, user_id):
            self.conn = conn
            self.user_id = user_id
        def create(self, prompt_id):
            # Insert a new writing attempt into the database
            # Database name is writing_submissions
            # Columns are: user_id, prompt_id, started_at, expires_at
            # Expires at should be 15 minutes after started_at
            started_at = datetime.datetime.utcnow()
            expires_at = started_at + datetime.timedelta(minutes=15)
            # Insert into database and return the new attempt_id
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO writing_submissions (user_id, prompt_id, started_at, expires_at)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                """, (self.user_id, prompt_id, started_at, expires_at))
                attempt_id = cursor.fetchone()[0]
                self.conn.commit()
            return {
                "attempt_id": attempt_id,
                "server_now": started_at.isoformat() + "Z",
                "started_at": started_at.isoformat() + "Z",
                "expires_at": expires_at.isoformat() + "Z"
            }
        def get_expiration(self, attempt_id):
            # Get the expiration time for a writing attempt
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    SELECT expires_at
                    FROM writing_submissions
                    WHERE id = %s AND user_id = %s
                """, (attempt_id, self.user_id))
                row = cursor.fetchone()
                if row:
                    return row[0]
                else:
                    return None
        def get_prompt(self, attempt_id):
            # Get the writing prompt associated with this attempt
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    SELECT wp.id, wp.title, wp.text, wp.language
                    FROM writing_submissions ws
                    JOIN writing_prompts wp ON ws.prompt_id = wp.id
                    WHERE ws.id = %s AND ws.user_id = %s
                """, (attempt_id, self.user_id))
                row = cursor.fetchone()
                if row:
                    return {
                        "id": row[0],
                        "title": row[1],
                        "text": row[2],
                        "language": row[3]
                    }
                else:
                    return None
        def submit(self, attempt_id, score, submitted_at):
            # Update the writing attempt with the user's score
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE writing_submissions
                    SET score = %s, submitted_at = %s
                    WHERE id = %s AND user_id = %s
                """, (score, submitted_at, attempt_id, self.user_id))
                self.conn.commit()
            return {
                "status": "ok"
            }