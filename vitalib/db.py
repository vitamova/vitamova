from urllib import request

import psycopg2
import os
import datetime
import random

# Create environment variables
def source_profile(file_path):
    with open(file_path) as f:
        for line in f:
            if line.startswith('export '):
                # Strip out 'export ' and split by '=' to get the key and value
                key, value = line[len('export '):].strip().split('=', 1)
                # Remove surrounding quotes from value if they exist
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                os.environ[key] = value

# Use the function to source the profile
source_profile(os.path.expanduser("~/.profile"))
# DB password is in ˜/data/db_password.txt
with open(os.path.expanduser("~/data/db_pw.txt"), "r") as f:
    DB_PASSWORD = f.read().strip()

# Map language codes to their full names to use for table names
LANGUAGE_MAP = {
    "es": "spanish",
    "ru": "russian",
    # Add more languages here as needed
}

# Database connection
class connection:
    @staticmethod
    def open():
        conn = psycopg2.connect(
            dbname="vitamova",
            user="webapp",
            password=DB_PASSWORD,
            host="vitamova-db.cluster-cartvcorpihi.us-east-1.rds.amazonaws.com",
            port="5432"
        )
        return conn
    @staticmethod
    def close(conn):
        #Commit changes and close the connection
        conn.commit()
        conn.close()

#Retrieve user information
class user_info:
    class add:
        def __init__(self, conn, username):
            self.username = username
            self.conn = conn
        def new(self, language):
            #Add the user to the user_info table
            #Make the last_article_read yesterday
            yesterday = str((datetime.datetime.now() - datetime.timedelta(days=1)).date())
            #Make the points 0
            with self.conn.cursor() as cur:
                cur.execute("INSERT INTO user_info (username, language, last_article_read, points) VALUES (%s, %s, %s, 0)", (self.username, language, yesterday))
    class get:
        def __init__(self, conn, username):
            self.username = username
            self.conn = conn

        def language(self):
            with self.conn.cursor() as cur:
                cur.execute("SELECT language FROM user_info WHERE username=%s", (self.username,))
                return cur.fetchone()[0]

        def last_article_read(self):
            with self.conn.cursor() as cur:
                cur.execute("SELECT last_article_read FROM user_info WHERE username=%s", (self.username,))
                return cur.fetchone()[0]

        def points(self):
            with self.conn.cursor() as cur:
                cur.execute("SELECT points FROM user_info WHERE username=%s", (self.username,))
                return cur.fetchone()[0]
    class update:
        def __init__(self, conn, username):
            self.username = username
            self.conn = conn
        
        def points(self, add_points):
            #Add add_points to the current points
            with self.conn.cursor() as cur:
                cur.execute("SELECT points FROM user_info WHERE username=%s", (self.username,))
                points = cur.fetchone()[0]
            points += add_points
            with self.conn.cursor() as cur:
                cur.execute("UPDATE user_info SET points=%s WHERE username=%s", (points, self.username))
            #return the new points
            return points
        def language(self, language):
            with self.conn.cursor() as cur:
                cur.execute("UPDATE user_info SET language=%s WHERE username=%s", (language, self.username))
        def last_article_read(self, date):
            with self.conn.cursor() as cur:
                cur.execute("UPDATE user_info SET last_article_read=%s WHERE username=%s", (date, self.username))

class vocabulary:
    @staticmethod
    def add(conn, username, word, definition, example):
        #Get language from username using user_info class
        language = user_info.get(conn,username).language()
        vocab_table = "vocabulary"
        dict_table = "dictionary_"+language
        #if the word is not in the dictionary, add it with the definition and example
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM "+dict_table+" WHERE word=%s", (word,))
            if cur.fetchone() is None:
                print("Word", word, "is not in the dictionary, adding it now")
                cur.execute("INSERT INTO "+dict_table+" (word, definition, example) VALUES (%s, %s, %s)", (word, definition, example))
            else:
                print("Word", word, "is already in the dictionary")
        #Get the id of the word from the dictionary
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM "+dict_table+" WHERE word=%s", (word,))
            word_id = cur.fetchone()[0]
        #Print the word id
        print("The word "+word+" has an id of ", word_id)
        #If the word is in the vocabulary, change the level to 0 and the next review to tomorrow
        tomorrow = str((datetime.datetime.now() + datetime.timedelta(days=1)).date())
        with conn.cursor() as cur:
            cur.execute("SELECT word_id FROM "+vocab_table+" WHERE username=%s AND word_id=%s", (username, word_id))
            if cur.fetchone() is not None:
                print("Word", word, "is already in the vocabulary, resetting it now")
                cur.execute("UPDATE "+vocab_table+" SET level=0, next_review=%s WHERE username=%s AND word_id=%s", (tomorrow, username, word_id))
            #If the word is not in the vocabulary, add it with level 0 and next review tomorrow
            else:
                print("Word", word, "is not in the vocabulary, adding it now")
                cur.execute("INSERT INTO "+vocab_table+" (username, word_id, level, next_review) VALUES (%s, %s, 0, %s)", (username, word_id, tomorrow))
    class count:
        def __init__(self, conn, username):
            self.username = username
            self.conn = conn
            #Get the language from the username using user_info class
            self.language = user_info.get(self.conn, self.username).language()
        def all(self):
            with self.conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM vocabulary WHERE username=%s", (self.username,))
                return cur.fetchone()[0]
        def today(self):
            #This will return the number of words that need to be reviewed today
            #These will have a next_review date of today or earlier
            with self.conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM vocabulary WHERE username=%s AND next_review<=%s", (self.username, str(datetime.datetime.now().date())))
                return cur.fetchone()[0]
    class get:
        def __init__(self, conn, username):
            self.username = username
            self.conn = conn
            #Get the language from the username using user_info class
            self.language = user_info.get(self.conn, self.username).language()
        def all(self):
            #Get all words in the vocabulary
            with self.conn.cursor() as cur:
                cur.execute("SELECT word_id, level, next_review FROM vocabulary WHERE username=%s", (self.username,))
                return cur.fetchall()
        def today(self, quantity):
            #Get all words that need to be reviewed today
            with self.conn.cursor() as cur:
                #The quantity parameter will be used to limit the number of words returned
                #The older words will be returned first
                cur.execute("SELECT word_id FROM vocabulary WHERE username=%s AND next_review<=%s ORDER BY next_review LIMIT %s", (self.username, str(datetime.datetime.now().date()), quantity))
                word_list = cur.fetchall()
            #Now get all the words with matching word_id from the dictionary
            words = []
            for word_id in word_list:
                with self.conn.cursor() as cur:
                    cur.execute("SELECT id, word, definition, example FROM dictionary_"+self.language+" WHERE id=%s", (word_id,))
                    result = cur.fetchone()
                    if result is not None:
                        words.append({
                            "id": result[0], #We need to use id instead of word_id because we are getting the id from the dictionary table
                            "word": result[1],
                            "definition": result[2],
                            "example": result[3]
                        })
            return words

    class level:
        def __init__(self, conn, username):
            self.conn = conn
            self.username = username
            #Get the language from the username using user_info class
            self.language = user_info.get(self.conn, self.username).language()
        def increase(self, word_id):
            #We will use the ebbinghaus forgetting curve to determine the next review date
            #If the current level is 0, increase to 1 and the next review is 3 days from now
            #If the current level is 1, increase to 2 and the next review is 7 days from now
            #If the current level is 2, increase to 3 and the next review is 14 days from now
            #If the current level is 3, increase to 4 and the next review is 30 days from now
            #If the current level is 4, increase to 5 and the next review is 60 days from now
            #If the current level is 5, increase to 6 and the next review is in year 3000
            #6 is the highest level
            with self.conn.cursor() as cur:
                cur.execute("SELECT level FROM vocabulary WHERE username=%s AND word_id=%s", (self.username, word_id))
                level = cur.fetchone()[0]
            if level == 0:
                next_review = str((datetime.datetime.now() + datetime.timedelta(days=3)).date())
                level = 1
            elif level == 1:
                next_review = str((datetime.datetime.now() + datetime.timedelta(days=7)).date())
                level = 2
            elif level == 2:
                next_review = str((datetime.datetime.now() + datetime.timedelta(days=14)).date())
                level = 3
            elif level == 3:
                next_review = str((datetime.datetime.now() + datetime.timedelta(days=30)).date())
                level = 4
            elif level == 4:
                next_review = str((datetime.datetime.now() + datetime.timedelta(days=60)).date())
                level = 5
            elif level == 5:
                next_review = "3000-01-01"
                level = 6
            with self.conn.cursor() as cur:
                cur.execute("UPDATE vocabulary SET level=%s, next_review=%s WHERE username=%s AND word_id=%s", (level, next_review, self.username, word_id))

        def reset(self, word_id):
            #Reset word level to 0 and next review to tomorrow
            tomorrow = str((datetime.datetime.now() + datetime.timedelta(days=1)).date())
            with self.conn.cursor() as cur:
                cur.execute("UPDATE vocabulary SET level=0, next_review=%s WHERE username=%s AND word_id=%s", (tomorrow, self.username, word_id))

class Test:
    LEVEL_RANGES = {
        1: (1, 1500),
        2: (1501, 3000),
        3: (3001, 6000),
        4: (6001, 10000),
        5: (10001, 15000),
        6: (15001, None),
    }
    def __init__(self, conn, username, language):
        self.conn = conn
        self.username = username
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
                    psycopg2.sql.SQL("""
                    SELECT correct_answer, lemma_rank
                    FROM {}
                    WHERE id = %s
                    """).format(
                        psycopg2.sql.Identifier(f"{LANGUAGE_MAP[self.language]}_vocab_test_bank")
                    ),
                    [question_id]
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
            for level, (min_rank, max_rank) in Test.LEVEL_RANGES.items():
                count = fetch_counts.get(level, 0)

                if count <= 0:
                    continue

                if max_rank is None:
                    cursor.execute(
                        psycopg2.sql.SQL("""
                        SELECT id,
                            question,
                            correct_answer,
                            distractor_1,
                            distractor_2,
                            distractor_3
                        FROM {}
                        WHERE lemma_rank >= %s
                        ORDER BY RANDOM()
                        LIMIT %s
                        """).format(
                            psycopg2.sql.Identifier(f"{LANGUAGE_MAP[self.language]}_vocab_test_bank")
                        ), [min_rank, count]
                    )


                else:
                    cursor.execute(
                        psycopg2.sql.SQL("""
                        SELECT id,
                            question,
                            correct_answer,
                            distractor_1,
                            distractor_2,
                            distractor_3
                        FROM {}
                        WHERE lemma_rank BETWEEN %s AND %s
                        ORDER BY RANDOM()
                        LIMIT %s
                        """).format(
                            psycopg2.sql.Identifier(f"{LANGUAGE_MAP[self.language]}_vocab_test_bank")
                        ), [min_rank, max_rank, count]
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