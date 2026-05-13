import os
import datetime
import random

# Map language codes to their full names to use for table names
LANGUAGE_MAP = {
    "es": "Spanish",
    "ru": "Russian",
    # Add more languages here as needed
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
        LEVEL_RANGES = {
            1: (1, 1500),
            2: (1501, 3000),
            3: (3001, 6000),
            4: (6001, 10000),
            5: (10001, 15000),
            6: (15001, None),
        }
        def __init__(self, conn, user_id, language):
            self.conn = conn
            self.user_id = user_id
            self.language = language
        def score_result(self, answers):
            level_correct_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0}
            level_total_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0}

            level_weighted_correct = {
                1: 0.0,
                2: 0.0,
                3: 0.0,
                4: 0.0,
                5: 0.0,
                6: 0.0,
            }

            level_weighted_total = {
                1: 0.0,
                2: 0.0,
                3: 0.0,
                4: 0.0,
                5: 0.0,
                6: 0.0,
            }

            # Score all submitted answers.
            with self.conn.cursor() as cursor:
                for answer in answers:
                    question_id = answer.get("question_id")
                    selected_option = answer.get("selected_option")

                    if not question_id or selected_option is None:
                        continue

                    cursor.execute(
                        """
                        SELECT v.correct_answer, l.rank AS lemma_rank
                        FROM vocab_test_bank v
                        JOIN lemmas l
                            ON v.lemma_id = l.id
                        WHERE v.id = %s
                        AND l.language = %s
                        """,
                        [question_id, self.language]
                    )
                    row = cursor.fetchone()

                    if not row:
                        continue

                    correct_answer = row[0]
                    lemma_rank = row[1]

                    level = None
                    min_rank_for_level = None
                    max_rank_for_level = None

                    # Determine level from lemma_rank.
                    for lvl, (min_rank, max_rank) in self.LEVEL_RANGES.items():
                        if max_rank is None:
                            if lemma_rank >= min_rank:
                                level = lvl
                                min_rank_for_level = min_rank

                                # Level 6 has no natural upper bound in LEVEL_RANGES.
                                # This synthetic bound is only for rank weighting.
                                max_rank_for_level = min_rank + 5000
                                break

                        elif min_rank <= lemma_rank <= max_rank:
                            level = lvl
                            min_rank_for_level = min_rank
                            max_rank_for_level = max_rank
                            break

                    if not level:
                        continue

                    # Check correctness once, then reuse it for both normal and weighted scoring.
                    correct_value = int(
                        str(selected_option).strip().casefold()
                        == str(correct_answer).strip().casefold()
                    )

                    # Rank weight within the level.
                    # Earlier/easier words are around 1.0.
                    # Later/harder words are up to around 2.0.
                    level_span = max_rank_for_level - min_rank_for_level

                    if level_span <= 0:
                        rank_position = 0.0
                    else:
                        rank_position = (lemma_rank - min_rank_for_level) / level_span
                        rank_position = max(0.0, min(1.0, rank_position))

                    rank_weight = 1.0 + rank_position

                    level_total_counts[level] += 1
                    level_correct_counts[level] += correct_value

                    level_weighted_total[level] += rank_weight
                    level_weighted_correct[level] += correct_value * rank_weight

            # Find the first tested level below 80%.
            # Since the loop stops there, all earlier tested levels were 80%+.
            frontier_level = 1

            for lvl in range(1, 7):
                total = level_total_counts[lvl]
                correct = level_correct_counts[lvl]

                if total == 0:
                    continue

                accuracy = correct / total

                if accuracy < 0.8:
                    frontier_level = lvl
                    break
            else:
                frontier_level = 6

            # Calculate plain, unweighted accuracies for reporting/retest downgrade logic.
            frontier_accuracy = 0.0
            below_frontier_accuracy = 0.0
            above_frontier_accuracy_plain = 0.0

            frontier_total = level_total_counts[frontier_level]
            frontier_correct = level_correct_counts[frontier_level]

            if frontier_total > 0:
                frontier_accuracy = frontier_correct / frontier_total

            below_correct = 0
            below_total = 0

            for lvl in range(1, frontier_level):
                below_correct += level_correct_counts[lvl]
                below_total += level_total_counts[lvl]

            if below_total > 0:
                below_frontier_accuracy = below_correct / below_total

            above_correct = 0
            above_total = 0

            for lvl in range(frontier_level + 1, 7):
                above_correct += level_correct_counts[lvl]
                above_total += level_total_counts[lvl]

            if above_total > 0:
                above_frontier_accuracy_plain = above_correct / above_total

            base_score = 1000 * (frontier_level - 1)

            frontier_weighted_total = level_weighted_total[frontier_level]
            frontier_weighted_correct = level_weighted_correct[frontier_level]

            if frontier_weighted_total > 0:
                frontier_weighted_accuracy = (
                    frontier_weighted_correct / frontier_weighted_total
                )
            else:
                frontier_weighted_accuracy = 0.0

            entry_threshold = 0.40
            mastery_threshold = 0.80

            raw_bonus_progress = (
                (frontier_weighted_accuracy - entry_threshold)
                / (mastery_threshold - entry_threshold)
            )
            raw_bonus_progress = max(0.0, min(1.0, raw_bonus_progress))

            raw_bonus = round(999 * raw_bonus_progress)

            above_frontier_weighted_correct = 0.0
            above_frontier_weighted_total = 0.0

            # Confidence multiplier from all levels above the frontier.
            # Higher levels and harder ranks count more.
            for lvl in range(frontier_level + 1, 7):
                level_distance = lvl - frontier_level

                # frontier + 1 = 1.0x
                # frontier + 2 = 1.5x
                # frontier + 3 = 2.0x
                distance_weight = 1.0 + (0.5 * (level_distance - 1))

                above_frontier_weighted_correct += (
                    level_weighted_correct[lvl] * distance_weight
                )
                above_frontier_weighted_total += (
                    level_weighted_total[lvl] * distance_weight
                )

            if above_frontier_weighted_total > 0:
                above_frontier_accuracy = (
                    above_frontier_weighted_correct
                    / above_frontier_weighted_total
                )
            else:
                above_frontier_accuracy = 0.0

            # Sample confidence prevents tiny above-frontier samples from
            # over-influencing the multiplier.
            sample_confidence = min(1.0, above_frontier_weighted_total / 12.0)

            above_frontier_proof = above_frontier_accuracy * sample_confidence

            # Multiplier range: 0.70 to 1.00.
            confidence_multiplier = 0.70 + (0.30 * above_frontier_proof)

            bonus = round(raw_bonus * confidence_multiplier)

            score = base_score + bonus
            score = max(0, min(6000, score))

            return {
                "score": score,
                "frontier_level": frontier_level,
                "frontier_accuracy": round(frontier_accuracy, 2),
                "below_frontier_accuracy": round(below_frontier_accuracy, 2),
                "above_frontier_accuracy": round(above_frontier_accuracy_plain, 2),
            }

        def get_questions(self, fetch_counts):
            questions = []
            # ---------------------------------------------------------------------
            # Fetch diagnostic questions based on fetch_counts.
            # ---------------------------------------------------------------------
            with self.conn.cursor() as cursor:
                for level, (min_rank, max_rank) in Database.Test.LEVEL_RANGES.items():
                    count = fetch_counts.get(level, 0)

                    if count <= 0:
                        continue

                    if max_rank is None:
                        cursor.execute(
                            """
                            SELECT
                                v.id,
                                v.question,
                                v.correct_answer,
                                v.distractor_1,
                                v.distractor_2,
                                v.distractor_3
                            FROM vocab_test_bank v
                            JOIN lemmas l
                                ON v.lemma_id = l.id
                            WHERE l.language = %s
                            AND l.rank >= %s
                            ORDER BY RANDOM()
                            LIMIT %s
                            """,
                            [self.language, min_rank, count]
                        )


                    else:
                        cursor.execute(
                            """
                            SELECT
                                v.id,
                                v.question,
                                v.correct_answer,
                                v.distractor_1,
                                v.distractor_2,
                                v.distractor_3
                            FROM vocab_test_bank v
                            JOIN lemmas l
                                ON v.lemma_id = l.id
                            WHERE l.language = %s
                            AND l.rank BETWEEN %s AND %s
                            ORDER BY RANDOM()
                            LIMIT %s
                            """,
                            [self.language, min_rank, max_rank, count]
                        )

                    rows = cursor.fetchall()

                    for row in rows:
                        options = [
                            row[2],
                            row[3],
                            row[4],
                            row[5],
                        ]

                        random.shuffle(options)

                        questions.append({
                            "question_id": row[0],
                            "question": row[1],
                            "options": options,
                        })    
            return questions
        def flag(self, question_id):
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
                        self.user_id,
                        question_id,
                        self.language,
                        datetime.datetime.now(datetime.timezone.utc)
                    ]
                )
            return {"status": "flagged"}