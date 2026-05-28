import vitalib
import random
from scipy.stats import beta

class Test:
    class Get:
        def __init__(self, conn, user_id, language):
            self.conn = conn
            self.user_id = user_id
            self.language = language
        def edge_range(self):

            # Broad placement ranges.
            # These are intentionally wide because the first goal is to locate the user's general zone.
            broad_ranges = [
                (1, 3000),
                (3001, 10000),
                (10001, None)
            ]

            target_edge_width = 100
            max_narrowing_rounds = 8
            minimum_results_to_narrow = 4

            questions = []
            question_fetcher = vitalib.Database.Test.Questions(
                self.conn,
                self.user_id,
                self.language
            )

            # First, check whether the user has enough data to make any useful edge estimate.
            total_existing_results = 0

            for min_rank, max_rank in broad_ranges:
                results = question_fetcher.range_results(min_rank, max_rank)
                total_existing_results += results["total"]

            # If the user has very little data, do a broad pass instead of pretending
            # we can already identify a precise edge.
            if total_existing_results < 9:
                base_count = count // len(broad_ranges)
                remainder = count % len(broad_ranges)

                for index, (min_rank, max_rank) in enumerate(broad_ranges):
                    range_count = base_count

                    if index < remainder:
                        range_count += 1

                    if range_count <= 0:
                        continue

                    range_questions = question_fetcher.new(
                        min_rank=min_rank,
                        max_rank=max_rank,
                        count=range_count
                    )

                    questions.extend(range_questions)

                questions = Test.Format.questions(questions)
                questions = question_fetcher.append_lemma(questions)
                return questions

            # Pick the broad range most likely to contain the user's learning edge.
            best_min_rank = None
            best_max_rank = None
            best_score = -1

            for min_rank, max_rank in broad_ranges:
                results = question_fetcher.range_results(min_rank, max_rank)

                correct = results["correct"]
                incorrect = results["incorrect"]
                total = results["total"]

                alpha = correct + 1
                beta_param = incorrect + 1

                edge_probability = beta.cdf(0.80, alpha, beta_param) - beta.cdf(0.40, alpha, beta_param)
                evidence_weight = total / (total + 8)

                edge_score = edge_probability * evidence_weight

                if edge_score > best_score:
                    best_score = edge_score
                    best_min_rank = min_rank
                    best_max_rank = results["max_rank"]

            # If max_rank was None and there were results, range_results should have resolved it.
            # If it still did not resolve, use a practical temporary ceiling.
            if best_max_rank is None:
                best_max_rank = best_min_rank + 999

            current_min_rank = best_min_rank
            current_max_rank = best_max_rank

            # Narrow the selected range by repeatedly splitting it into thirds.
            narrowing_round = 0

            while narrowing_round < max_narrowing_rounds:
                current_width = current_max_rank - current_min_rank + 1

                if current_width <= target_edge_width:
                    break

                split_size = current_width // 3

                if split_size <= 0:
                    break

                range_1_min = current_min_rank
                range_1_max = current_min_rank + split_size - 1

                range_2_min = range_1_max + 1
                range_2_max = range_2_min + split_size - 1

                range_3_min = range_2_max + 1
                range_3_max = current_max_rank

                candidate_ranges = [
                    (range_1_min, range_1_max),
                    (range_2_min, range_2_max),
                    (range_3_min, range_3_max)
                ]

                best_candidate_min = current_min_rank
                best_candidate_max = current_max_rank
                best_candidate_score = -1
                best_candidate_total = 0

                for candidate_min_rank, candidate_max_rank in candidate_ranges:
                    results = question_fetcher.range_results(
                        candidate_min_rank,
                        candidate_max_rank
                    )

                    correct = results["correct"]
                    incorrect = results["incorrect"]
                    total = results["total"]

                    alpha = correct + 1
                    beta_param = incorrect + 1

                    edge_probability = beta.cdf(0.80, alpha, beta_param) - beta.cdf(0.40, alpha, beta_param)
                    evidence_weight = total / (total + 8)

                    edge_score = edge_probability * evidence_weight

                    if edge_score > best_candidate_score:
                        best_candidate_score = edge_score
                        best_candidate_min = candidate_min_rank
                        best_candidate_max = candidate_max_rank
                        best_candidate_total = total

                # If the best smaller range has almost no data, stop narrowing.
                # At this point, asking more questions in the current range is better
                # than making a fake-precise guess.
                if best_candidate_total < minimum_results_to_narrow:
                    break

                current_min_rank = best_candidate_min
                current_max_rank = best_candidate_max

                narrowing_round += 1
            return (current_min_rank, current_max_rank)
        def new_questions(self, count):
            if count <= 0:
                return []
            
            question_fetcher = vitalib.Database.Test.Questions(
                self.conn,
                self.user_id,
                self.language
            )

            current_min_rank, current_max_rank = self.edge_range()

            # Get half of the questions from the edge range
            questions = question_fetcher.new(
                min_rank=current_min_rank,
                max_rank=current_max_rank,
                count=count//2
            )

            # Get the level_mastery dictionary
            level_mastery = self.level_mastery()
            # Find the level with the highest mastery confidence
            best_level = max(level_mastery, key=lambda level: level_mastery[level]["mastery_confidence"])
            # The other half of the questions should come from best_level
            # This helps the user achieve a sense of accomplishment by reinforcing their strongest level while they work on their edge.
            best_level_min_rank = (best_level * 1000) + 1
            best_level_max_rank = best_level_min_rank + 999
            questions.extend(question_fetcher.new(
                min_rank=best_level_min_rank,
                max_rank=best_level_max_rank,
                count=count - (count//2)
            ))

            questions = Test.Format.questions(questions)
            questions = question_fetcher.append_lemma(questions)

            return questions
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
            # Log results
            logged = vitalib.Database.Test.Questions(self.conn, self.user_id, self.language).log_result(results)
            if logged["status"] != "logged" or not logged:
                raise Exception("Failed to log results")
            missed = [r for r in results if not r["is_correct"]]
            missed = vitalib.Database.Test.Questions(self.conn, self.user_id, self.language).append_lemma(missed)
            missed = vitalib.Database.Test.Questions(self.conn, self.user_id, self.language).append_options(missed)
            missed = vitalib.Database.Test.Questions(self.conn, self.user_id, self.language).append_question_text(missed)
            for m in missed:
                m["correct_answer"] = m["lemma"]["lemma"]
            return missed
        def new_score(self):
            score_result = 0
            # Get the per_level_results for the user
            per_level_results = vitalib.Database.Test.Questions(self.conn, self.user_id, self.language).per_level_results()
            eval_dict = {}
            for level in per_level_results:
                correct = per_level_results[level].get("correct", 0)
                incorrect = per_level_results[level].get("incorrect", 0)
                eval_dict[level] = {}
                eval_dict[level]["mastery_confidence"] = beta.sf(0.80, correct + 1, incorrect + 1)
                eval_dict[level]["entry_confidence"] = beta.sf(0.40, correct + 1, incorrect + 1)
            frontier = 1
            for level in sorted(eval_dict.keys()):
                if level < len(list(eval_dict.keys())):
                    next_level = level + 1
                    if eval_dict[level]["mastery_confidence"] >= 0.9 and eval_dict[next_level]["entry_confidence"] >= 0.9:
                        frontier = next_level
            base_score = 1000 * (frontier - 1)
            if frontier < len(list(eval_dict.keys())):
                bonus = 1000 * eval_dict[frontier]["mastery_confidence"] * eval_dict[frontier + 1]["entry_confidence"]
            else:
                bonus = 1000 * eval_dict[frontier]["mastery_confidence"]
            score_result = base_score + bonus
            if score_result >= 1000:
                confidence = "solid"
            elif eval_dict[1]["mastery_confidence"] < 0.1 or eval_dict[2]["entry_confidence"] < 0.1:
                confidence = "solid"
            else:
                confidence = "rough"
            return {
                "score": round(score_result),
                "confidence": confidence
            }
        def level_mastery(self, question_mastery_threshold = 0.80):
            result = {}
            # Get user's current level
            current_level = vitalib.Database.UserInfo.Get(
                self.conn,
                self.user_id
            ).level(self.language)

            # Get the number of lemmas for this language
            total_lemmas = vitalib.Database.Vocab.Get(
                self.conn,
                self.user_id,
                self.language
            ).total_lemmas()

            # If the user is level 0, start at ranks 1-1000.
            # If the user is level 3, start at ranks 3001-4000.
            min_rank = (current_level * 1000) + 1

            while min_rank <= total_lemmas:
                max_rank = min(min_rank + 999, total_lemmas)
                associated_level = (min_rank - 1) // 1000

                coverage_result = vitalib.Database.Vocab.Get(
                    self.conn,
                    self.user_id,
                    self.language
                ).coverage(
                    min_rank,
                    max_rank
                )

                range_result = vitalib.Database.Test.Questions(
                    self.conn,
                    self.user_id,
                    self.language
                ).range_results(
                    min_rank,
                    max_rank
                )

                coverage = coverage_result["coverage"]

                correct = range_result["correct"]
                incorrect = range_result["incorrect"]

                mastery_confidence = beta.sf(
                    question_mastery_threshold,
                    correct + 1,
                    incorrect + 1
                )
                result[associated_level] = {
                    "coverage": coverage,
                    "mastery_confidence": mastery_confidence
                }
                min_rank += 1000
            return result
        def new_level(self):
            coverage_mastery_threshold = 0.80
            question_mastery_threshold = 0.80
            confidence_threshold = 0.90

            level_mastery = self.level_mastery(question_mastery_threshold)
            new_level = sorted(list(level_mastery.keys()))[0]

            for level in sorted(level_mastery.keys()):
                coverage = level_mastery[level]["coverage"]
                mastery_confidence = level_mastery[level]["mastery_confidence"]

                mastered_by_coverage = coverage >= coverage_mastery_threshold

                mastered_by_questions = (
                    mastery_confidence >= confidence_threshold
                )

                if mastered_by_coverage or mastered_by_questions:
                    new_level = (min_rank // 1000) + 1

            return new_level


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