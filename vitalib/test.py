import vitalib
import random

class Test:
    class Get:
        def __init__(self, conn, user_id, language):
            self.conn = conn
            self.user_id = user_id
            self.language = language
        def any_questions(self, type, score, batch=None):
            # Get frontier based on score
            frontier = min((score // 1000) + 1, 6)
            fetch_counts = {}
            if type == "diagnostic":
                # Batch must be provided for diagnostic questions
                if batch is None:
                    raise ValueError("Batch must be provided for diagnostic questions")
                # If batch is 1, fetch_counts should be 3 each
                if batch == 1:
                    fetch_counts = {i: 3 for i in range(1, 7)}
                    questions = vitalib.Database.Test.Questions(self.conn, self.language).any(fetch_counts)
                    return Test.Format.questions(questions)
                # If batch is anything else fetch_counts should be based on frontier
        def new_questions(self, type, score):
            # Get frontier based on score
            frontier = min((score // 1000) + 1, 6)
            fetch_counts = {}
            if type == "vocab_builder":
                # Get 8 questions from the frontier level 1 from a level above and 1 from a level below
                # If frontier is 1 do an 8/2 split
                # If frontier is 6 do a 8/2 split but with the below level instead of the above level
                if frontier == 1:
                    fetch_counts[1] = 8
                    fetch_counts[2] = 2
                elif frontier == 6:
                    fetch_counts[5] = 2
                    fetch_counts[6] = 8
                else:
                    fetch_counts[frontier - 1] = 1
                    fetch_counts[frontier] = 8
                    fetch_counts[frontier + 1] = 1
            # Fetch questions based on fetch_counts
            questions = vitalib.Database.Test.Questions(self.conn, self.language).new(self.user_id, fetch_counts)
            return Test.Format.questions(questions)
        def results(self, answers):
            example_return = {
                "status": "ok",
                "language": "es",
                "total_questions": 10,
                "correct_count": 7,
                "incorrect_count": 3,
                "missed_questions": [
                    {
                    "question_id": 102,
                    "lemma_id": 55,
                    "prompt": "What does 'casa' mean?",
                    "context": null,
                    "selected_option_id": "C",
                    "selected_answer_text": "book",
                    "correct_option_id": "A",
                    "correct_answer_text": "house",
                    "options": [
                        {
                        "option_id": "A",
                        "text": "house"
                        },
                        {
                        "option_id": "B",
                        "text": "dog"
                        },
                        {
                        "option_id": "C",
                        "text": "book"
                        },
                        {
                        "option_id": "D",
                        "text": "street"
                        }
                    ],
                    "lemma": {
                        "id": 55,
                        "language": "es",
                        "rank": 125,
                        "lemma": "casa",
                        "translation": "house",
                        "definition": "A building or place where people live."
                    }
                    }
                ]
                }
            correct_answers = vitalib.Database.Test.Answers(self.conn).correct(answers)
    class Format:
        @staticmethod
        def questions(rows):
            questions = []

            for row in rows:
                question_id, question, correct_answer, distractor_1, distractor_2, distractor_3 = row

                options = [
                    correct_answer,
                    distractor_1,
                    distractor_2,
                    distractor_3
                ]

                random.shuffle(options)

                questions.append({
                    "question_id": question_id,
                    "question": question,
                    "options": options
                })

            return questions