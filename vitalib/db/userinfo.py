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
    "second_level",
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
        def score(self, language, new_score):
            language = language.strip().lower()

            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT target_language, second_target_language
                    FROM registered_user
                    WHERE user_id = %s
                    """,
                    (self.user_id,)
                )

                row = cur.fetchone()

            if not row:
                raise ValueError(f"No registered_user found for user_id {self.user_id}")

            target_language, second_target_language = row

            if target_language and language == target_language.strip().lower():
                self.data(vocab_score=new_score)
                return

            if second_target_language and language == second_target_language.strip().lower():
                self.data(second_vocab_score=new_score)
                return

            raise ValueError(
                f"Language '{language}' does not match any target language for user_id {self.user_id}"
            )
        def level(self, language, new_level):
            # Update the level for the language. If it's for target_language update level, if it's for second_target_language update second_level
            language = language.strip().lower()
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT target_language, second_target_language
                    FROM registered_user
                    WHERE user_id = %s
                    """,
                    (self.user_id,)
                )

                row = cur.fetchone()

            if not row:
                raise ValueError(f"No registered_user found for user_id {self.user_id}")
            target_language, second_target_language = row
            if target_language and language == target_language.strip().lower():
                self.data(level=new_level)
                return
            if second_target_language and language == second_target_language.strip().lower():
                self.data(second_level=new_level)
                return
            raise ValueError(
                f"Language '{language}' does not match any target language for user_id {self.user_id}"
            )
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
        
        def score(self, language):
            language = language.strip().lower()

            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT target_language, second_target_language, vocab_score, second_vocab_score
                    FROM registered_user
                    WHERE user_id = %s
                    """,
                    (self.user_id,)
                )

                row = cur.fetchone()

            if not row:
                raise ValueError(f"No registered_user found for user_id {self.user_id}")

            target_language, second_target_language, vocab_score, second_vocab_score = row

            if target_language and language == target_language.strip().lower():
                return vocab_score

            if second_target_language and language == second_target_language.strip().lower():
                return second_vocab_score

            raise ValueError(
                f"Language '{language}' does not match any target language for user_id {self.user_id}"
            )
        def level(self, language):
            # Same as score, if it's for target_language get level
            # If it's for second_target_language get second_level
            language = language.strip().lower()
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT target_language, second_target_language, level, second_level
                    FROM registered_user
                    WHERE user_id = %s
                    """,
                    (self.user_id,)
                )

                row = cur.fetchone()

            if not row:
                raise ValueError(f"No registered_user found for user_id {self.user_id}")

            target_language, second_target_language, level, second_level = row

            if target_language and language == target_language.strip().lower():
                return level

            if second_target_language and language == second_target_language.strip().lower():
                return second_level

            raise ValueError(
                f"Language '{language}' does not match any target language for user_id {self.user_id}"
            )
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