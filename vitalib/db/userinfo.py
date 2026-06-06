import datetime
import vitalib

ALLOWED_COLUMNS = {
    "native_language",
    "target_language",
    "level",
    "subscribed",
    "subscription_expiration",
    "stripe_customer_id",
    "second_target_language",
    "date_created",
    "date_updated"
}

class UserInfo:

    class Create:
        def __init__(self, conn, user_id):
            self.conn = conn
            self.user_id = user_id
        def data(self, **fields):
            allowed_columns = ALLOWED_COLUMNS | {"user_id"}

            # We're gonna automatically give the user 30 days of subscription
            fields["subscribed"] = True
            fields["subscription_expiration"] = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=30)).date()

            fields["user_id"] = self.user_id

            invalid_columns = set(fields.keys()) - allowed_columns
            if invalid_columns:
                raise ValueError(f"Invalid column name(s): {', '.join(invalid_columns)}")

            columns = ", ".join(fields.keys())
            placeholders = ", ".join(["%s"] * len(fields))
            values = list(fields.values())

            with self.conn.cursor() as cur:
                query = f"""
                    INSERT INTO registered_user ({columns})
                    VALUES ({placeholders})
                    RETURNING id
                """
                cur.execute(query, values)
                new_registered_user_id = cur.fetchone()[0]

            self.conn.commit()
            return new_registered_user_id
        def stats(self, language):
            # This will create a new record in user_stats
            # Set the level, next_level_coverage, and writing_level to 0 for the language
            language = language.strip().lower()
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_stats (user_id, language, level, next_level_coverage, writing_level)
                    VALUES (%s, %s, 0, 0, 0)
                    """,
                    (self.user_id, language)
                )
            self.conn.commit()
    class Update:
        def __init__(self, conn, user_id):
            self.conn = conn
            self.user_id = user_id
        def data(self, **fields):
            if not fields:
                return

            invalid_columns = set(fields.keys()) - ALLOWED_COLUMNS
            if invalid_columns:
                raise ValueError(f"Invalid column name(s): {', '.join(invalid_columns)}")

            set_clause = ", ".join([f"{column} = %s" for column in fields.keys()])
            values = list(fields.values())
            values.append(self.user_id)

            with self.conn.cursor() as cur:
                query = f"""
                    UPDATE registered_user
                    SET {set_clause}
                    WHERE user_id = %s
                """
                cur.execute(query, values)

            self.conn.commit()
        def level(self, language, new_level):
            # Update the level in the user_stats table for the given language
            language = language.strip().lower()
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT language FROM user_stats
                    WHERE user_id = %s AND language = %s
                    """,
                    (self.user_id, language)
                )
                row = cur.fetchone()
                if row:
                    # If a record already exists for this user and language, update it
                    cur.execute(
                        """
                        UPDATE user_stats
                        SET level = %s
                        WHERE user_id = %s AND language = %s
                        """,
                        (new_level, self.user_id, language)
                    )
                else:
                    # Otherwise, raise an error since we should always have a record in user_stats for each language
                    raise ValueError(f"No user_stats found for user_id {self.user_id} and language {language}")
            self.conn.commit()
        def next_level_coverage(self, language, coverage):
            # Update the next_level_coverage in the user_stats table for the given language
            language = language.strip().lower()
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT language FROM user_stats
                    WHERE user_id = %s AND language = %s
                    """,
                    (self.user_id, language)
                )
                row = cur.fetchone()
                if row:
                    # If a record already exists for this user and language, update it
                    cur.execute(
                        """
                        UPDATE user_stats
                        SET next_level_coverage = %s
                        WHERE user_id = %s AND language = %s
                        """,
                        (coverage, self.user_id, language)
                    )
                else:
                    # Otherwise, raise an error since we should always have a record in user_stats for each language
                    raise ValueError(f"No user_stats found for user_id {self.user_id} and language {language}")
            self.conn.commit()

    class Get:
        def __init__(self, conn, user_id):
            self.conn = conn
            self.user_id = user_id
        def data(self, *columns):
            if not columns:
                columns = tuple(ALLOWED_COLUMNS)

            invalid_columns = set(columns) - ALLOWED_COLUMNS
            if invalid_columns:
                raise ValueError(f"Invalid column name(s): {', '.join(invalid_columns)}")

            column_list = ", ".join(columns)

            with self.conn.cursor() as cur:
                query = f"""
                    SELECT {column_list}
                    FROM registered_user
                    WHERE user_id = %s
                """
                cur.execute(query, (self.user_id,))
                row = cur.fetchone()

            if not row:
                return None

            return dict(zip(columns, row))
        
        def level(self, language):
            # Now we're going to pull this from user_stats table
            # language is now a column so we just need to get the level value for the language and user_id
            language = language.strip().lower()
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT level FROM user_stats
                    WHERE user_id = %s AND language = %s
                    """,
                    (self.user_id, language)
                )
                row = cur.fetchone()
            if not row:
                raise ValueError(f"No user_stats found for user_id {self.user_id} and language {language}")
            return row[0]
        
        def next_level_coverage(self, language):
            language = language.strip().lower()
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT next_level_coverage FROM user_stats
                    WHERE user_id = %s AND language = %s
                    """,
                    (self.user_id, language)
                )
                row = cur.fetchone()
            if not row:
                raise ValueError(f"No user_stats found for user_id {self.user_id} and language {language}")
            return row[0]
        
        def languages(self):
            with self.conn.cursor() as cur:
                cur.execute("SELECT target_language, second_target_language FROM registered_user WHERE user_id=%s", (self.user_id,))
                row = cur.fetchone()
                if row:
                    if row[1] and row[1].strip() != "":
                        return [
                            {"code": row[0], "name": vitalib.Transform.Language(row[0]).code_to_name()},
                            {"code": row[1], "name": vitalib.Transform.Language(row[1]).code_to_name() if row[1] else None}
                        ]
                    else:
                        return [
                            {"code": row[0], "name": vitalib.Transform.Language(row[0]).code_to_name()}
                        ]
                else:
                    return []