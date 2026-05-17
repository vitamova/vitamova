import os
import datetime
import random

# Map language codes to their full names to use for table names
LANGUAGE_MAP = {
    "es": "Spanish",
    "ru": "Russian",
    # Add more languages here as needed
}

LEVEL_RANGES = {
    1: (1, 1500),
    2: (1501, 3000),
    3: (3001, 6000),
    4: (6001, 10000),
    5: (10001, 15000),
    6: (15001, None),
}

class Database:
    #Retrieve user information
    class UserInfo:
        ALLOWED_COLUMNS = {
            "native_language",
            "target_language",
            "vocab_score",
            "subscribed",
            "subscription_expiration",
            "stripe_customer_id",
            "second_target_language",
            "second_vocab_score"
        }
        class Create:
            def __init__(self, conn, user_id):
                self.conn = conn
                self.user_id = user_id

            def data(self, **fields):
                allowed_columns = Database.UserInfo.ALLOWED_COLUMNS | {"user_id"}

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

                invalid_columns = set(fields.keys()) - Database.UserInfo.ALLOWED_COLUMNS
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
        class Get:
            def __init__(self, conn, user_id):
                self.conn = conn
                self.user_id = user_id
            def data(self, *columns):
                if not columns:
                    columns = tuple(Database.UserInfo.ALLOWED_COLUMNS)

                invalid_columns = set(columns) - Database.UserInfo.ALLOWED_COLUMNS
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
            def languages(self):
                with self.conn.cursor() as cur:
                    cur.execute("SELECT target_language, second_target_language FROM registered_user WHERE user_id=%s", (self.user_id,))
                    row = cur.fetchone()
                    if row:
                        return [
                            {"code": row[0], "name": LANGUAGE_MAP.get(row[0], row[0])},
                            {"code": row[1], "name": LANGUAGE_MAP.get(row[1], row[1])}
                        ]
                    return []

    class Vocab:
        class Get:
            def __init__(self, conn, user_id, language):
                self.conn = conn
                self.user_id = user_id
                self.language = language
            def review_count(self):
                with self.conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT COUNT(*)
                        FROM user_vocabulary uv
                        JOIN lemmas l
                            ON uv.lemma_id = l.id
                        WHERE uv.user_id = %s
                        AND l.language = %s
                        AND uv.next_review_at IS NOT NULL
                        AND uv.next_review_at < %s
                        """,
                        [
                            self.user_id,
                            self.language,
                            datetime.datetime.now(datetime.timezone.utc)
                        ]
                    )
                    review_count = cursor.fetchone()[0]

                return review_count
            def words():
                pass
        class Add:
            def __init__(self, conn, user_id):
                self.conn = conn
                self.user_id = user_id
            def lemma(self, lemma_id):
                # Columns are: id, user_id, lemma_id, status, review_stage, 
                # next_review_at, last_reviewed_at, times_seen, times_correct, times_incorrect
                # created_at, updated_at
                # Note lemma_id is unique across languages, so we don't need to specify language here
                with self.conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT 1
                        FROM user_vocabulary
                        WHERE user_id = %s
                        AND lemma_id = %s
                        """,
                        [self.user_id, lemma_id]
                    )
                    if cursor.fetchone():
                        return {"status": "already_exists"}
                    
                    # Since we're adding a new lemma, we can set most of these to their initial values.
                    cursor.execute(
                        """
                        INSERT INTO user_vocabulary (
                            user_id,
                            lemma_id,
                            status,
                            review_stage,
                            next_review_at,
                            last_reviewed_at,
                            times_seen,
                            times_correct,
                            times_incorrect,
                            created_at,
                            updated_at
                        ) VALUES (%s, %s, %s, 'learning', 0, NULL, NULL, 0, 0, 0, %s, %s)
                        ON CONFLICT (user_id, lemma_id, language) DO NOTHING
                        """,
                        [
                            self.user_id,
                            lemma_id,
                            datetime.datetime.now(datetime.timezone.utc),
                            datetime.datetime.now(datetime.timezone.utc)
                        ]
                    )
                return {"status": "added"}

    class Test:
        class Questions:
            def __init__(self, conn, language):
                self.conn = conn
                self.language = language

            def any(self, fetch_counts):
                questions = []

                with self.conn.cursor() as cursor:
                    for level, count in fetch_counts.items():
                        if count <= 0:
                            continue

                        min_rank, max_rank = LEVEL_RANGES[level]

                        sql = """
                            SELECT
                                vtb.id,
                                vtb.question,
                                vtb.correct_answer,
                                vtb.distractor_1,
                                vtb.distractor_2,
                                vtb.distractor_3
                            FROM vocab_test_bank vtb
                            JOIN lemmas l ON l.id = vtb.lemma_id
                            WHERE l.language = %s
                            AND l.rank >= %s
                        """

                        params = [self.language, min_rank]

                        if max_rank is not None:
                            sql += " AND l.rank <= %s"
                            params.append(max_rank)

                        sql += " ORDER BY RANDOM() LIMIT %s"
                        params.append(count)

                        cursor.execute(sql, params)
                        questions.extend(cursor.fetchall())

                return questions

            def new(self, user_id, fetch_counts):
                questions = []

                with self.conn.cursor() as cursor:
                    for level, count in fetch_counts.items():
                        if count <= 0:
                            continue

                        min_rank, max_rank = LEVEL_RANGES[level]

                        sql = """
                            SELECT
                                vtb.id,
                                vtb.question,
                                vtb.correct_answer,
                                vtb.distractor_1,
                                vtb.distractor_2,
                                vtb.distractor_3
                            FROM vocab_test_bank vtb
                            JOIN lemmas l ON l.id = vtb.lemma_id
                            WHERE l.language = %s
                            AND l.rank >= %s
                            AND NOT EXISTS (
                                SELECT 1
                                FROM user_vocabulary uv
                                WHERE uv.user_id = %s
                                    AND uv.lemma_id = vtb.lemma_id
                            )
                        """

                        params = [self.language, min_rank, user_id]

                        if max_rank is not None:
                            sql += " AND l.rank <= %s"
                            params.append(max_rank)

                        sql += " ORDER BY RANDOM() LIMIT %s"
                        params.append(count)

                        cursor.execute(sql, params)
                        questions.extend(cursor.fetchall())

                return questions
            
            def flag(self, user_id, question_id):
                with self.conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO flagged_questions (
                            user_id,
                            question_id,
                            language,
                            flagged_at
                        )
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (user_id, question_id, language)
                        DO UPDATE SET flagged_at = EXCLUDED.flagged_at
                        """,
                        [
                            user_id,
                            question_id,
                            self.language,
                            datetime.datetime.now(datetime.timezone.utc)
                        ]
                    )
                return {"status": "flagged"}
        class Answers:
            def __init__(self, conn):
                self.conn = conn
            def correct(self, questions):
                question_ids = [q["question_id"] for q in questions]

                if not question_ids:
                    return {}

                with self.conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT id, correct_answer
                        FROM vocab_test_bank
                        WHERE id = ANY(%s);
                        """,
                        [question_ids]
                    )

                    rows = cursor.fetchall()

                return {
                    question_id: correct_answer
                    for question_id, correct_answer in rows
                }


