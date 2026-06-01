import datetime
import vitalib

REVIEW_STAGE_INTERVALS = {
    0: datetime.timedelta(0), # When someone gets a word wrong, sets back to 0 for immediate review
    1: datetime.timedelta(hours=18),
    2: datetime.timedelta(days=2, hours=18),
    3: datetime.timedelta(days=6, hours=18),
    4: datetime.timedelta(days=13, hours=18),
    5: datetime.timedelta(days=29, hours=18),
    6: datetime.timedelta(days=59, hours=18),
    7: datetime.timedelta(days=119, hours=18)
}

class Vocab:
    class Get:
        def __init__(self, conn, user_id, language):
            self.conn = conn
            self.user_id = user_id
            self.language = language
            self.native_language = vitalib.Database.UserInfo.Get(conn, user_id).data("native_language")["native_language"]
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
        def review_items(self):
            # Need to get lemma_id, lemma, pronunciation, translation, definition,
            # part_of_speech, and example_sentence.
            # Filter by language and user_id.
            # Only return words where next_review_at is in the past.

            with self.conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        l.id,
                        l.lemma,
                        l.pronunciation,
                        lt.translation,
                        l.definition,
                        l.pos,
                        s.sentence AS example_sentence
                    FROM user_vocabulary uv
                    JOIN lemmas l
                        ON uv.lemma_id = l.id
                    LEFT JOIN lemma_translations lt
                        ON lt.lemma_id = l.id
                        AND lt.native_language = %s
                    LEFT JOIN LATERAL (
                        SELECT sentence
                        FROM sentences
                        WHERE lemma_id = l.id
                        AND language = l.language
                        ORDER BY date_created ASC
                        LIMIT 1
                    ) s ON TRUE
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

            items = []

            for row in rows:
                item = {
                    "lemma_id": row[0],
                    "lemma": row[1],
                    "translation": row[3],
                    "definition": row[4],
                    "part_of_speech": row[5],
                    "example_sentence": row[6],
                }

                if row[2] is not None:
                    item["pronunciation"] = row[2]

                items.append(item)

            return items
        def total_lemmas(self):
            with self.conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM lemmas
                    WHERE language = %s
                    """,
                    [self.language]
                )
                lemma_count = cursor.fetchone()[0]

            return lemma_count
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
        def lemma_by_name(self, lemma_name):
            # The lemma_name is the lemma column in the lemmas table
            # Return the id and rank
            with self.conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, rank, definition
                    FROM lemmas
                    WHERE language = %s
                    AND lemma = %s
                    """,
                    [
                        self.language,
                        lemma_name
                    ]
                )
                row = cursor.fetchone()
            if not row:
                return None
            return {
                "lemma_id": row[0],
                "rank": row[1],
                "definition": row[2]
            }
        def coverage(self, min_rank, max_rank):
            if min_rank is None:
                min_rank = 1

            if max_rank is not None and max_rank < min_rank:
                raise ValueError("max_rank must be greater than or equal to min_rank.")

            sql = """
                WITH range_lemmas AS (
                    SELECT
                        id
                    FROM lemmas
                    WHERE language = %s
                    AND rank >= %s
            """

            params = [
                self.language,
                min_rank
            ]

            if max_rank is not None:
                sql += " AND rank <= %s"
                params.append(max_rank)

            sql += """
                ),

                vocabulary_points AS (
                    SELECT
                        COALESCE(
                            SUM(
                                CASE
                                    WHEN uv.review_stage IS NULL THEN 0
                                    WHEN uv.review_stage <= 1 THEN 0
                                    WHEN uv.review_stage >= 7 THEN 6
                                    ELSE uv.review_stage - 1
                                END
                            ),
                            0
                        ) AS earned_points
                    FROM range_lemmas rl
                    LEFT JOIN user_vocabulary uv
                        ON uv.lemma_id = rl.id
                        AND uv.user_id = %s
                ),

                correct_question_lemmas AS (
                    SELECT DISTINCT
                        vtb.lemma_id
                    FROM user_vocab_question_results uvqr
                    JOIN vocab_test_bank vtb
                        ON uvqr.question_id = vtb.id
                    JOIN range_lemmas rl
                        ON rl.id = vtb.lemma_id
                    WHERE uvqr.user_id = %s
                    AND uvqr.correct = true
                    AND NOT EXISTS (
                        SELECT 1
                        FROM user_vocabulary uv
                        WHERE uv.user_id = %s
                        AND uv.lemma_id = vtb.lemma_id
                    )
                ),

                question_points AS (
                    SELECT
                        COUNT(*) * 6 AS earned_points
                    FROM correct_question_lemmas
                )

                SELECT
                    COUNT(*) AS total_words,
                    vocabulary_points.earned_points,
                    question_points.earned_points
                FROM range_lemmas
                CROSS JOIN vocabulary_points
                CROSS JOIN question_points
                GROUP BY
                    vocabulary_points.earned_points,
                    question_points.earned_points
            """

            params.extend([
                self.user_id,
                self.user_id,
                self.user_id
            ])

            with self.conn.cursor() as cursor:
                cursor.execute(sql, params)
                row = cursor.fetchone()

            if row is None:
                total_words = 0
                vocabulary_points = 0
                question_points = 0
            else:
                total_words = row[0] or 0
                vocabulary_points = row[1] or 0
                question_points = row[2] or 0

            earned_points = vocabulary_points + question_points
            max_points = total_words * 6

            if max_points == 0:
                coverage_ratio = 0
            else:
                coverage_ratio = earned_points / max_points

            return {
                "min_rank": min_rank,
                "max_rank": max_rank,
                "total_words": total_words,
                "vocabulary_points": vocabulary_points,
                "question_points": question_points,
                "earned_points": earned_points,
                "max_points": max_points,
                "coverage": coverage_ratio,
                "coverage_percent": round(coverage_ratio * 100, 2)
            }
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
                    ) VALUES (%s, %s, 'learning', 1, %s, NULL, 0, 0, 0, %s, %s)
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

                #If the current review stage is 7, keep it at 7 but set status to "learned"
                # Otherwise, increment the review stage by 1
                if current_review_stage >= 7:
                    new_review_stage = 7
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
                        datetime.datetime.now(datetime.timezone.utc),
                        datetime.datetime.now(datetime.timezone.utc),
                        datetime.datetime.now(datetime.timezone.utc),
                        self.user_id,
                        lemma_id
                    ]
                )
            return {"status": "updated"}