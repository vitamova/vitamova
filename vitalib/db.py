import datetime
import random
import vitalib
import psycopg2
from concurrent.futures import ThreadPoolExecutor, TimeoutError

LEVEL_RANGES = {
    1: (1, 1500),
    2: (1501, 3000),
    3: (3001, 6000),
    4: (6001, 10000),
    5: (10001, 15000),
    6: (15001, None),
}

REVIEW_STAGE_INTERVALS = {
    0: datetime.timedelta(hours=18),
    1: datetime.timedelta(days=2, hours=18),
    2: datetime.timedelta(days=6, hours=18),
    3: datetime.timedelta(days=13, hours=18),
    4: datetime.timedelta(days=29, hours=18),
    5: datetime.timedelta(days=59, hours=18),
    6: datetime.timedelta(days=119, hours=18)
}

class Database:
    class Status:
        def __init__(self, conn_params):
            self.conn_params = conn_params

        def get(self):
            def quick_check():
                conn = psycopg2.connect(
                    **self.conn_params,
                    connect_timeout=1
                )

                try:
                    with conn.cursor() as cursor:
                        cursor.execute("SELECT 1;")
                        result = cursor.fetchone()

                    return result is not None and result[0] == 1

                finally:
                    conn.close()

            try:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(quick_check)
                    return future.result(timeout=0.5)

            except TimeoutError:
                return False

            except Exception:
                return False

        def start(self):
            try:
                conn = psycopg2.connect(
                    **self.conn_params,
                    connect_timeout=15
                )

                try:
                    with conn.cursor() as cursor:
                        cursor.execute("SELECT 1;")
                        result = cursor.fetchone()

                    if result is not None and result[0] == 1:
                        return {
                            "status": "ok",
                            "message": "Database start successful."
                        }

                    return {
                        "status": "error",
                        "error": "Database did not return the expected response."
                    }

                finally:
                    conn.close()

            except Exception as error:
                return {
                    "status": "error",
                    "error": str(error)
                }
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
            "second_vocab_score",
            "date_created",
            "date_updated"
        }
        class Create:
            def __init__(self, conn, user_id):
                self.conn = conn
                self.user_id = user_id

            def data(self, **fields):
                allowed_columns = Database.UserInfo.ALLOWED_COLUMNS | {"user_id"}

                # We're gonna automatically give the user 30 days of subscription
                fields["subscribed"] = True
                fields["subscription_expiration"] = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=30)

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

    class Vocab:
        class Get:
            def __init__(self, conn, user_id, language):
                self.conn = conn
                self.user_id = user_id
                self.language = language
                self.native_language = Database.UserInfo.Get(conn, user_id).data("native_language")["native_language"]
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
            def words(self):
                # Need to get lemma_id, lemma, pronunciation, translation, and definition
                # Also need to filter by language and user_id
                # And should only be words that have next_review_at in the past
                with self.conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT
                            l.id,
                            l.lemma,
                            l.pronunciation,
                            lt.translation,
                            l.definition
                        FROM user_vocabulary uv
                        JOIN lemmas l
                            ON uv.lemma_id = l.id
                        LEFT JOIN lemma_translations lt
                            ON lt.lemma_id = l.id
                        AND lt.native_language = %s
                        WHERE uv.user_id = %s
                        AND l.language = %s
                        AND uv.next_review_at IS NOT NULL
                        AND uv.next_review_at < %s
                        """,
                        [
                            self.native_language,
                            self.user_id,
                            self.language,
                            datetime.datetime.now(datetime.timezone.utc)
                        ]
                    )
                    rows = cursor.fetchall()
                # Return a list of dicts with all the lemmas that need to be reviewed
                return [
                    {
                        "lemma_id": row[0],
                        "lemma": row[1],
                        "pronunciation": row[2],
                        "translation": row[3],
                        "definition": row[4]
                    }
                    for row in rows
                ]
            def lemma(self, lemma_id):
                with self.conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT
                            l.id,
                            l.lemma,
                            l.pronunciation,
                            lt.translation,
                            l.definition
                        FROM lemmas l
                        LEFT JOIN lemma_translations lt
                            ON lt.lemma_id = l.id
                        AND lt.native_language = %s
                        WHERE l.id = %s
                        AND l.language = %s
                        """,
                        [
                            self.native_language,
                            lemma_id,
                            self.language
                        ]
                    )
                    row = cursor.fetchone()
                if not row:
                    return None
                return {
                    "lemma_id": row[0],
                    "lemma": row[1],
                    "pronunciation": row[2],
                    "translation": row[3],
                    "definition": row[4]
                }
            def lemma_starts_with(self, prefix):
                # Return up to 5 lemmas that start with the given prefix for the user's target language
                # Include translation when available in the user's native language

                with self.conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT 
                            l.id,
                            l.lemma,
                            l.pos,
                            l.definition,
                            lt.translation
                        FROM lemmas l
                        LEFT JOIN lemma_translations lt
                            ON lt.lemma_id = l.id
                            AND lt.native_language = %s
                        WHERE l.language = %s
                        AND l.lemma ILIKE %s
                        ORDER BY l.rank ASC
                        LIMIT 5
                        """,
                        [
                            self.native_language,
                            self.language,
                            prefix + '%'
                        ]
                    )
                    rows = cursor.fetchall()

                return [
                    {
                        "lemma_id": row[0],
                        "lemma": row[1],
                        "part_of_speech": row[2],
                        "definition": row[3],
                        "translation": row[4]
                    }
                    for row in rows
                ]
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
                    # Next review will be in 1 day, so we can set next_review_at to now + 1 day
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
                        ) VALUES (%s, %s, 'learning', 0, %s, NULL, 0, 0, 0, %s, %s)
                        """,
                        [
                            self.user_id,
                            lemma_id,
                            datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours = 18),
                            datetime.datetime.now(datetime.timezone.utc),
                            datetime.datetime.now(datetime.timezone.utc)
                        ]
                    )
                    # We should also return the lemma that was added to the user's vocabulary
                    cursor.execute(
                        """
                        SELECT lemma
                        FROM lemmas
                        WHERE id = %s
                        """,
                        [lemma_id]
                    )
                    lemma = cursor.fetchone()[0]
                return {"status": "added", "lemma": lemma}
        class Update:
            def __init__(self, conn, user_id):
                self.conn = conn
                self.user_id = user_id
            def correct(self, lemma_id):
                # Need to update the user_vocabulary entry for this lemma_id and user_id
                # It's correct so we should increment times_seen and times_correct
                # updated_at and last_reviewed_at should be set to now
                # review_stage should be incremented by 1 and next_review_at should be set based on the new review_stage
                with self.conn.cursor() as cursor:
                    # Let's first get the current review_stage for this lemma_id and user_id
                    cursor.execute(
                        """
                        SELECT review_stage
                        FROM user_vocabulary
                        WHERE user_id = %s
                        AND lemma_id = %s
                        """,
                        [self.user_id, lemma_id]
                    )
                    row = cursor.fetchone()
                    if not row:
                        return {"status": "not_found"}
                    current_review_stage = row[0]

                    #If the current review stage is 6, keep it at 6 but set status to "learned"
                    # Otherwise, increment the review stage by 1
                    if current_review_stage >= 6:
                        new_review_stage = 6
                        status = "learned"
                    else:
                        new_review_stage = current_review_stage + 1
                        status = "learning"
                    cursor.execute(
                        """
                        UPDATE user_vocabulary
                        SET times_seen = times_seen + 1,
                            times_correct = times_correct + 1,
                            review_stage = %s,
                            next_review_at = %s,
                            last_reviewed_at = %s,
                            status = %s,
                            updated_at = %s
                        WHERE user_id = %s
                        AND lemma_id = %s
                        """,
                        [
                            new_review_stage,
                            datetime.datetime.now(datetime.timezone.utc) + REVIEW_STAGE_INTERVALS[new_review_stage],
                            datetime.datetime.now(datetime.timezone.utc),
                            status,
                            datetime.datetime.now(datetime.timezone.utc),
                            self.user_id,
                            lemma_id
                        ]
                    )
                return {"status": "updated"}
            def incorrect(self, lemma_id):
                # Need to update the user_vocabulary entry for this lemma_id and user_id
                # It's incorrect so we should increment times_seen and times_incorrect
                # updated_at and last_reviewed_at should be set to now
                # review_stage should be set back to 0 and next_review_at should be set to now + 18 hours
                with self.conn.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE user_vocabulary
                        SET times_seen = times_seen + 1,
                            times_incorrect = times_incorrect + 1,
                            review_stage = 0,
                            next_review_at = %s,
                            last_reviewed_at = %s,
                            updated_at = %s
                        WHERE user_id = %s
                        AND lemma_id = %s
                        """,
                        [
                            datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours = 18),
                            datetime.datetime.now(datetime.timezone.utc),
                            datetime.datetime.now(datetime.timezone.utc),
                            self.user_id,
                            lemma_id
                        ]
                    )
                return {"status": "updated"}

    class Test:
        class Questions:
            def __init__(self, conn, user_id, language):
                self.conn = conn
                self.user_id = user_id
                self.language = language
                self.native_language = Database.UserInfo.Get(conn, user_id).data("native_language")["native_language"]
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

            def new(self, fetch_counts):
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
                            AND NOT EXISTS (
                                SELECT 1
                                FROM user_vocab_question_results uvqr
                                WHERE uvqr.user_id = %s
                                    AND uvqr.question_id = vtb.id
                            )
                        """

                        params = [
                            self.language,
                            min_rank,
                            self.user_id,
                            self.user_id
                        ]

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
            def log_result(self, results):
                if not results:
                    return {"status": "logged", "count": 0}

                answered_at = datetime.datetime.now(datetime.timezone.utc)

                rows = [
                    (
                        self.user_id,
                        result["question_id"],
                        result["is_correct"],
                        answered_at
                    )
                    for result in results
                ]

                with self.conn.cursor() as cursor:
                    cursor.executemany(
                        """
                        INSERT INTO user_vocab_question_results (
                            user_id,
                            question_id,
                            correct,
                            answered_at
                        )
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (user_id, question_id)
                        DO UPDATE SET
                            correct = EXCLUDED.correct,
                            answered_at = EXCLUDED.answered_at
                        """,
                        rows
                    )

                self.conn.commit()

                return {"status": "logged", "count": len(rows)}
            def per_level_results(self):
                # For each level in LEVEL_RANGES
                # Return the number correct and number incorrect
                results = {}
                with self.conn.cursor() as cursor:
                    for level, (min_rank, max_rank) in LEVEL_RANGES.items():
                        sql = """
                            SELECT
                                COUNT(*) FILTER (WHERE correct = true) AS correct_count,
                                COUNT(*) FILTER (WHERE correct = false) AS incorrect_count
                            FROM user_vocab_question_results uvqr
                            JOIN vocab_test_bank vtb ON uvqr.question_id = vtb.id
                            JOIN lemmas l ON vtb.lemma_id = l.id
                            WHERE uvqr.user_id = %s
                            AND l.language = %s
                            AND l.rank >= %s
                        """

                        params = [self.user_id, self.language, min_rank]

                        if max_rank is not None:
                            sql += " AND l.rank <= %s"
                            params.append(max_rank)

                        cursor.execute(sql, params)
                        row = cursor.fetchone()
                        results[level] = {
                            "correct": row[0],
                            "incorrect": row[1]
                        }
                self.conn.commit()
                return results
            def append_lemma_rank(self, questions):
                question_ids = [q["question_id"] for q in questions]
                if not question_ids:
                    return questions
                with self.conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT vtb.id, l.rank
                        FROM vocab_test_bank vtb
                        JOIN lemmas l ON vtb.lemma_id = l.id
                        WHERE vtb.id = ANY(%s)
                        """,
                        [question_ids]
                    )
                    rank_map = {row[0]: row[1] for row in cursor.fetchall()}
                for question in questions:
                    question_id = question["question_id"]
                    question["lemma_rank"] = rank_map.get(question_id)
                return questions
            def append_lemma(self, questions):
                question_ids = [q["question_id"] for q in questions]

                if not question_ids:
                    return questions

                with self.conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT
                            vtb.id AS question_id,
                            l.id AS lemma_id,
                            l.lemma,
                            lt.translation,
                            l.definition
                        FROM vocab_test_bank vtb
                        JOIN lemmas l
                            ON vtb.lemma_id = l.id
                        LEFT JOIN lemma_translations lt
                            ON lt.lemma_id = l.id
                        AND lt.native_language = %s
                        WHERE vtb.id = ANY(%s)
                        """,
                        [
                            self.native_language,
                            question_ids
                        ]
                    )

                    lemma_map = {
                        row[0]: {
                            "id": row[1],
                            "lemma": row[2],
                            "translation": row[3],
                            "definition": row[4]
                        }
                        for row in cursor.fetchall()
                    }

                for question in questions:
                    question_id = question["question_id"]
                    question["lemma"] = lemma_map.get(question_id)

                return questions
            def append_options(self, questions):
                #Access the database to get the options
                #Options should be shuffled
                question_ids = [q["question_id"] for q in questions]
                if not question_ids:
                    return questions
                with self.conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT id, correct_answer, distractor_1, distractor_2, distractor_3
                        FROM vocab_test_bank
                        WHERE id = ANY(%s)
                        """,
                        [question_ids]
                    )
                    options_map = {
                        row[0]: [row[1], row[2], row[3], row[4]]
                        for row in cursor.fetchall()
                    }
                for question in questions:
                    question_id = question["question_id"]
                    options = options_map.get(question_id, [])
                    random.shuffle(options)
                    question["options"] = options
                return questions
            def append_question_text(self, questions):
                question_ids = [q["question_id"] for q in questions]
                if not question_ids:
                    return questions
                with self.conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT id, question
                        FROM vocab_test_bank
                        WHERE id = ANY(%s)
                        """,
                        [question_ids]
                    )
                    question_map = {row[0]: row[1] for row in cursor.fetchall()}
                for question in questions:
                    question_id = question["question_id"]
                    question["question"] = question_map.get(question_id)
                return questions
            def get_lemma_id(self, question_id):
                with self.conn.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT lemma_id
                        FROM vocab_test_bank
                        WHERE id = %s
                        """,
                        [question_id]
                    )
                    row = cursor.fetchone()
                if not row:
                    return None
                return row[0]
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


