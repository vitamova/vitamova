import vitalib
import random

LEVEL_RANGES = {
    1: (1, 1500),
    2: (1501, 3000),
    3: (3001, 6000),
    4: (6001, 10000),
    5: (10001, 15000),
    6: (15001, None),
}

class Test:
    class Get:
        def __init__(self, conn, user_id, language):
            self.conn = conn
            self.user_id = user_id
            self.language = language
        def any_questions(self, type, frontier, batch=None):
            # First we need to set fetch_counts based on the parameters
            fetch_counts = { i : 0 for i in range(1, 7) }
            if type == "diagnostic":
                # Batch must be provided for diagnostic questions
                if batch is None:
                    raise ValueError("Batch must be provided for diagnostic questions")
                # If batch is 1, fetch_counts should be 3 each
                if batch == 1:
                    fetch_counts = {i: 3 for i in range(1, 7)}
                else:
                    if frontier == 1:
                        fetch_counts[1] = 12
                        fetch_counts[2] = 6
                    elif frontier == 6:
                        fetch_counts[5] = 6
                        fetch_counts[6] = 12
                    else:
                        fetch_counts[frontier - 1] = 4
                        fetch_counts[frontier] = 10
                        fetch_counts[frontier + 1] = 4
            elif type == "retest":
                # Get 50 questions total with a 30/10/10 split or 35/15 split if frontier is 1 or 6
                if frontier == 1:
                    fetch_counts[1] = 35
                    fetch_counts[2] = 15
                elif frontier == 6:
                    fetch_counts[5] = 15
                    fetch_counts[6] = 35
                else:
                    fetch_counts[frontier - 1] = 10
                    fetch_counts[frontier] = 30
                    fetch_counts[frontier + 1] = 10
            
            # Now it's simple, just get the questions and return them formatted
            questions = vitalib.Database.Test.Questions(self.conn, self.language).any(fetch_counts)
            return Test.Format.questions(questions)
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
            correct_answers = vitalib.Database.Test.Answers(self.conn).correct(answers)
            # For each answer, compare correct to selected
            for answer in answers:
                question_id = answer["question_id"]
                selected_option = answer["selected_option"]
                correct_answer = correct_answers.get(question_id)
                is_correct = (selected_option == correct_answer)
                answer["is_correct"] = is_correct
            return answers
        def missed(self, answers):
            results = self.results(answers)
            missed = [r for r in results if not r["is_correct"]]
            missed = vitalib.Database.Test.Questions(self.conn, self.language).append_lemma(missed)
            missed = vitalib.Database.Test.Questions(self.conn, self.language).append_options(missed)
            for m in missed:
                m["correct_answer"] = m["lemma"]["lemma"]
            return missed
        def frontier(self, answers):
            # All we need to do is find the first level where the user got between 40% and 80% correct
            results = self.results(answers)
            # Append the lemma rank
            results = vitalib.Database.Test.Questions(self.conn, self.language).append_lemma_rank(results)
            frontier = 1
            for level in LEVEL_RANGES:
                level_results = [r for r in results if LEVEL_RANGES[level][0] <= r["lemma_rank"] <= (LEVEL_RANGES[level][1] or float('inf'))]
                if not level_results:
                    continue
                correct_count = sum(1 for r in level_results if r["is_correct"])
                total_count = len(level_results)
                accuracy = correct_count / total_count
                if 0.40 <= accuracy < 0.80:
                    frontier = level
                    break
            return frontier
        def bonus(self, results, frontier_level):
            level_weighted_total = { i: 0.0 for i in range(1, 7) }

            level_weighted_correct = { i: 0.0 for i in range(1, 7) }

            for result in results:
                lemma_rank = result["lemma_rank"]

                level = None

                for lvl, rank_range in LEVEL_RANGES.items():
                    min_rank, max_rank = rank_range

                    if max_rank is None:
                        if lemma_rank >= min_rank:
                            level = lvl
                            break
                    else:
                        if min_rank <= lemma_rank <= max_rank:
                            level = lvl
                            break

                if level is None:
                    continue

                level_weighted_total[level] += 1.0

                if result["is_correct"]:
                    level_weighted_correct[level] += 1.0

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

            for lvl in range(frontier_level + 1, 7):
                level_distance = lvl - frontier_level

                distance_weight = 1.0 + (0.5 * (level_distance - 1))

                above_frontier_weighted_correct += (
                    level_weighted_correct[lvl] * distance_weight
                )

                above_frontier_weighted_total += (
                    level_weighted_total[lvl] * distance_weight
                )

            if above_frontier_weighted_total > 0:
                above_frontier_accuracy = (
                    above_frontier_weighted_correct / above_frontier_weighted_total
                )
            else:
                above_frontier_accuracy = 0.0

            sample_confidence = min(1.0, above_frontier_weighted_total / 12.0)

            above_frontier_proof = above_frontier_accuracy * sample_confidence

            confidence_multiplier = 0.70 + (0.30 * above_frontier_proof)

            bonus = round(raw_bonus * confidence_multiplier)

            return bonus
        def score(self, answers):
            # Calculate the frontier level and base score
            frontier = self.frontier(answers)
            base_score = 1000 * (frontier - 1)

            # Now get the detailed results to calculate the bonus
            results = self.results(answers)
            results = vitalib.Database.Test.Questions(self.conn, self.language).append_lemma_rank(results)

            bonus = self.bonus(results, frontier)
            total_score = base_score + bonus

            # Get user's current score
            current_score = vitalib.Database.UserInfo.Get(self.conn, self.user_id).score(self.language)
            # Update user's score if total_score is higher
            if total_score > current_score:
                vitalib.Database.UserInfo.Update(self.conn, self.user_id).score(self.language, total_score)

            return total_score
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