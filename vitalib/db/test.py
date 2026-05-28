import datetime
import random
import vitalib

LEVEL_RANGES = {
    1: (1, 1500),
    2: (1501, 3000),
    3: (3001, 6000),
    4: (6001, 10000),
    5: (10001, 15000),
    6: (15001, None),
}

class Test:
    class Questions:
        def __init__(self, conn, user_id, language):
            self.conn = conn
            self.user_id = user_id
            self.language = language
            self.native_language = vitalib.Database.UserInfo.Get(conn, user_id).data("native_language")["native_language"]
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