import vitalib
import random
from scipy.stats import beta
from collections import Counter

class Test:
    class Get:
        def __init__(self, conn, user_id, language):
            self.conn = conn
            self.user_id = user_id
            self.language = language
            self.current_level = vitalib.Database.UserInfo.Get(
                conn,
                user_id
            ).level(language)
        def edge_range(self):
            # Return the most likely learning edge range based on the user's existing results.
            # This does not fetch new questions. It only looks at available user data.

            broad_ranges = [
                (1, 3000),
                (3001, 10000),
                (10001, None)
            ]

            target_edge_width = 100
            max_narrowing_rounds = 8
            minimum_results_to_narrow = 4

            question_fetcher = vitalib.Database.Test.Questions(
                self.conn,
                self.user_id,
                self.language
            )

            total_existing_results = 0

            for min_rank, max_rank in broad_ranges:
                results = question_fetcher.range_results(min_rank, max_rank)
                total_existing_results += results["total"]

            # If there is not enough data to estimate an edge, return a broad default.
            # This gives the app a safe starting range without pretending to be precise.
            if total_existing_results == 0:
                return (1, 3000)

            # Pick the broad range most likely to contain the user's learning edge.
            best_min_rank = None
            best_max_rank = None
            best_score = -1

            for min_rank, max_rank in broad_ranges:
                results = question_fetcher.range_results(min_rank, max_rank)

                correct = results["correct"]
                incorrect = results["incorrect"]
                total = results["total"]

                if total == 0:
                    continue

                alpha = correct + 1
                beta_param = incorrect + 1

                # Learning edge means the user is probably neither lost nor fully comfortable.
                # This estimates P(40% <= true accuracy <= 80%).
                edge_probability = beta.cdf(
                    0.80,
                    alpha,
                    beta_param
                ) - beta.cdf(
                    0.40,
                    alpha,
                    beta_param
                )

                # Ranges with very little data should count less.
                evidence_weight = total / (total + 8)

                edge_score = edge_probability * evidence_weight

                if edge_score > best_score:
                    best_score = edge_score
                    best_min_rank = min_rank
                    best_max_rank = results["max_rank"]

            # Fallback in case all ranges had zero usable data somehow.
            if best_min_rank is None:
                return (1, 3000)

            # If the open-ended range did not resolve to a real max rank, use a temporary window.
            if best_max_rank is None:
                best_max_rank = best_min_rank + 999

            current_min_rank = best_min_rank
            current_max_rank = best_max_rank

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

                    if total == 0:
                        continue

                    alpha = correct + 1
                    beta_param = incorrect + 1

                    edge_probability = beta.cdf(
                        0.80,
                        alpha,
                        beta_param
                    ) - beta.cdf(
                        0.40,
                        alpha,
                        beta_param
                    )

                    evidence_weight = total / (total + 8)

                    edge_score = edge_probability * evidence_weight

                    if edge_score > best_candidate_score:
                        best_candidate_score = edge_score
                        best_candidate_min = candidate_min_rank
                        best_candidate_max = candidate_max_rank
                        best_candidate_total = total

                # Stop narrowing if the smaller range does not have enough evidence.
                # This avoids returning a fake-precise 100-rank edge from almost no data.
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

            level_mastery = self.level_mastery()
            next_level = self.current_level + 1

            # Case 1:
            # The user has not answered any questions yet.
            #
            # Checking correct + incorrect is safer than comparing a calculated
            # floating-point confidence directly with 0.2.
            has_no_activity = all(
                level_mastery[level]["correct"]
                + level_mastery[level]["incorrect"] == 0
                for level in level_mastery
            )

            if has_no_activity:
                fetch_weights = {
                    2: 1,
                    4: 3,
                    5: 3,
                    6: 3,
                    7: 3,
                    8: 2,
                    10: 2,
                    13: 1,
                    18: 1,
                    25: 1
                }

            # Case 3:
            # The user's current level is established and the next level is
            # confidently not mastered. Focus completely on the next level.
            elif (
                self.current_level > 0
                and next_level in level_mastery
                and level_mastery[next_level]["mastery_confidence"] <= 0.10
            ):
                fetch_weights = {
                    next_level: 1
                }

            # Case 2:
            # The user has answered questions, but the learning frontier has not
            # yet been fully confirmed.
            else:
                candidate_pairs = []

                sorted_levels = sorted(level_mastery)

                for lower_level in sorted_levels:
                    upper_level = lower_level + 1

                    if upper_level not in level_mastery:
                        continue

                    lower_confidence = level_mastery[lower_level][
                        "mastery_confidence"
                    ]
                    upper_confidence = level_mastery[upper_level][
                        "mastery_confidence"
                    ]

                    confidence_drop = max(
                        lower_confidence - upper_confidence,
                        0
                    )

                    # A strong frontier has:
                    # 1. High confidence in mastery of the lower level.
                    # 2. Low confidence in mastery of the upper level.
                    # 3. A substantial drop between the two.
                    frontier_score = (
                        lower_confidence
                        * (1 - upper_confidence)
                        * confidence_drop
                    )

                    candidate_pairs.append({
                        "lower_level": lower_level,
                        "upper_level": upper_level,
                        "lower_confidence": lower_confidence,
                        "upper_confidence": upper_confidence,
                        "frontier_score": frontier_score
                    })

                if not candidate_pairs:
                    raise ValueError(
                        "Unable to identify any adjacent vocabulary levels."
                    )

                best_pair = max(
                    candidate_pairs,
                    key=lambda pair: pair["frontier_score"]
                )

                lower_level = best_pair["lower_level"]
                upper_level = best_pair["upper_level"]

                lower_confidence = best_pair["lower_confidence"]
                upper_confidence = best_pair["upper_confidence"]

                # Set fetch_weights to zero for lower level, upper level, and next level
                fetch_weights = {}
                fetch_weights[lower_level] = 0
                fetch_weights[upper_level] = 0
                fetch_weights[next_level] = 0
                # Doing it this way in case two of the levels are the same

                # Give 40% to the lower level to push for mastery
                # Give 40% to the next level to keep building coverage
                # Give 20% to the upper level 
                fetch_weights[lower_level] += 0.40
                fetch_weights[upper_level] += 0.20
                fetch_weights[next_level] += 0.40
                # Not sure if this is good, but it's a band-aid for now

            considered_levels = list(fetch_weights.keys())
            level_weights = list(fetch_weights.values())

            selected_levels = random.choices(
                population=considered_levels,
                weights=level_weights,
                k=count
            )

            # random.choices() returns the selected levels themselves.
            # Count how many questions should come from each selected level.
            selected_level_counts = Counter(selected_levels)

            questions = []

            for level, level_count in selected_level_counts.items():
                min_rank = ((level - 1) * 1000) + 1
                max_rank = min_rank + 999

                questions.extend(
                    question_fetcher.new(
                        min_rank=min_rank,
                        max_rank=max_rank,
                        count=level_count
                    )
                )

            questions = Test.Format.questions(questions)
            questions = question_fetcher.append_lemma(questions)
            random.shuffle(questions)

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
        def level_mastery(self, question_mastery_threshold = 0.80):
            result = {}
            # Get user's current level

            # Get the number of lemmas for this language
            total_lemmas = vitalib.Database.Vocab.Get(
                self.conn,
                self.user_id,
                self.language
            ).total_lemmas()

            # If the user is level 0, start at ranks 1-1000.
            # If the user is level 3, start at ranks 3001-4000.
            min_rank = (self.current_level * 1000) + 1

            while min_rank <= total_lemmas:
                max_rank = min(min_rank + 999, total_lemmas)
                associated_level = (min_rank - 1) // 1000 + 1

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
                    "mastery_confidence": mastery_confidence,
                    "correct": correct,
                    "incorrect": incorrect
                }
                min_rank += 1000
            return result
        def new_level(self):
            coverage_mastery_threshold = 0.80
            question_mastery_threshold = 0.80
            confidence_threshold = 0.90

            level_mastery = self.level_mastery(question_mastery_threshold)
            updated_level = self.current_level

            for level in sorted(level_mastery.keys()):
                coverage = level_mastery[level]["coverage"]
                mastery_confidence = level_mastery[level]["mastery_confidence"]

                mastered_by_coverage = coverage >= coverage_mastery_threshold

                mastered_by_questions = (
                    mastery_confidence >= confidence_threshold
                )

                if mastered_by_coverage or mastered_by_questions:
                    updated_level = level

            return updated_level


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