import json
import re
import time
from collections import Counter
import vitalib

WRITING_SCORE_LEVELS = {
    1: {
        "title": "Level 1 - Unintelligible",
        "description": "The intended meaning cannot be reliably determined, or the response is completely unrelated to the prompt."
    },
    2: {
        "title": "Level 2 - Mostly Unintelligible",
        "description": "Some isolated ideas are understandable, but most of the message is unclear. The response may barely address the prompt or may be mostly off-topic."
    },
    3: {
        "title": "Level 3 - Difficult to Understand",
        "description": "The general topic can be inferred, but understanding requires substantial effort. The response may address the prompt only partially or unclearly."
    },
    4: {
        "title": "Level 4 - Understandable with Significant Effort",
        "description": "Most of the message can be understood, but frequent errors and awkward phrasing slow the reader down. The response makes a clear attempt to answer the prompt."
    },
    5: {
        "title": "Level 5 - Understandable",
        "description": "The message is generally clear. Errors are common but rarely prevent understanding. The response answers the prompt in a basic but recognizable way."
    },
    6: {
        "title": "Level 6 - Comfortable",
        "description": "The writing communicates effectively. Errors and awkward phrasing are noticeable but not distracting. The response answers the prompt clearly and includes some relevant detail."
    },
    7: {
        "title": "Level 7 - Strong",
        "description": "The writing is clear, organized, and mostly natural. Minor issues do not interfere with communication. The response answers the prompt directly and includes relevant supporting details."
    },
    8: {
        "title": "Level 8 - Advanced",
        "description": "The writing communicates detailed ideas clearly and naturally. There are few noticeable weaknesses. The response fully answers the prompt and develops the topic well."
    },
    9: {
        "title": "Level 9 - Near-Native",
        "description": "The writing feels natural and sophisticated. The response fully answers the prompt with nuance, detail, and strong control of tone."
    },
    10: {
        "title": "Level 10 - Expert",
        "description": "The writing demonstrates exceptional command of language, style, nuance, and audience awareness. The response answers the prompt completely and would be considered excellent by highly educated native speakers."
    }
}


class Writing:
    class Get:
        def __init__(self, conn, user_id, language):
            self.conn = conn
            self.user_id = user_id
            self.language = language

        def score(self, prompt_text, text):
            model_rounds = [
                {"openai": "gpt-4.1-mini", "gemini": "gemini-2.5-flash"},
                {"openai": "gpt-4.1", "gemini": "gemini-2.5-pro"},
                {"openai": "gpt-4o", "gemini": "gemini-1.5-pro"}
            ]

            prompt = f"""
You are evaluating a language learner's writing in {self.language}.

The learner was given this writing prompt:

{prompt_text}

The learner wrote this response:

{text}

Evaluate the response using exactly one score from 1 to 10.

Your score should evaluate how effectively the learner communicates in {self.language}, including whether the learner actually answered the prompt.

Use this rubric:

{json.dumps(WRITING_SCORE_LEVELS, indent=4)}

Important rules:
- Choose the level description that best matches the response.
- Consider both writing quality and prompt relevance.
- If the response is well-written but does not answer the prompt, lower the score significantly.
- If the response answers the prompt but has weak language, score based on the language quality.
- Do not reward advanced ideas if the writing itself is unclear.
- Do not punish simple writing if it is clear, natural, effective, and directly answers the prompt.
- Return only valid JSON.
- Do not include markdown.

Return this exact JSON structure:
{{
    "score": 1
}}
""".strip()

            scores = []
            model_results = []
            failures = []

            for model_pair in model_rounds:
                round_scores = []

                attempts = [
                    {"provider": "openai", "model": model_pair["openai"]},
                    {"provider": "openai", "model": model_pair["openai"]},
                    {"provider": "gemini", "model": model_pair["gemini"]},
                    {"provider": "gemini", "model": model_pair["gemini"]},
                ]

                for attempt_info in attempts:
                    try:
                        if attempt_info["provider"] == "openai":
                            bot = vitalib.Chatbot.OpenAI(attempt_info["model"])
                        else:
                            bot = vitalib.Chatbot.Gemini(attempt_info["model"])

                        response = bot.send_message(prompt)

                        try:
                            data = json.loads(response)
                            score_value = int(data["score"])
                        except Exception:
                            match = re.search(r"\b(10|[1-9])\b", response)
                            if not match:
                                raise ValueError(f"Could not extract score from response: {response}")
                            score_value = int(match.group(1))

                        if score_value < 1 or score_value > 10:
                            raise ValueError(f"Score out of range: {score_value}")

                        scores.append(score_value)
                        round_scores.append(score_value)

                        model_results.append({
                            "provider": attempt_info["provider"],
                            "model": attempt_info["model"],
                            "score": score_value
                        })

                        if len(round_scores) >= 2:
                            if abs(round_scores[-1] - round_scores[-2]) <= 1:
                                final_score = min(round_scores[-1], round_scores[-2])
                                return {
                                    "status": "success",
                                    "value": final_score,
                                    "method": "two_model_agreement",
                                    "model_results": model_results,
                                    "failures": failures,
                                    "title": WRITING_SCORE_LEVELS[final_score]["title"],
                                    "description": WRITING_SCORE_LEVELS[final_score]["description"]
                                }

                        counts = Counter(scores)
                        highest_count = max(counts.values())

                        if highest_count > 1:
                            tied_scores = [
                                score for score, count in counts.items()
                                if count == highest_count
                            ]

                            final_score = min(tied_scores)

                            return {
                                "status": "success",
                                "value": final_score,
                                "method": "majority_vote",
                                "model_results": model_results,
                                "failures": failures,
                                "title": WRITING_SCORE_LEVELS[final_score]["title"],
                                "description": WRITING_SCORE_LEVELS[final_score]["description"]
                            }

                    except Exception as e:
                        failures.append({
                            "provider": attempt_info["provider"],
                            "model": attempt_info["model"],
                            "error": str(e)
                        })
                        time.sleep(1)

            if scores:
                final_score = min(scores)

                return {
                    "status": "success",
                    "method": "lowest_score",
                    "model_results": model_results,
                    "failures": failures,
                    "value": final_score,
                    "title": WRITING_SCORE_LEVELS[final_score]["title"],
                    "description": WRITING_SCORE_LEVELS[final_score]["description"]
                }

            raise ValueError(f"All scoring attempts failed: {failures}")

        def improvements(self, prompt_text, text, score):
            current_level = WRITING_SCORE_LEVELS[score]
            next_score = score + 1

            if next_score > 10:
                next_score = 10

            next_level = WRITING_SCORE_LEVELS[next_score]

            prompt = f"""
You are helping a language learner improve their writing in {self.language}.

The learner was given this writing prompt:

{prompt_text}

The learner wrote this response:

{text}

The writing received this score:

Score: {score}
Title: {current_level["title"]}
Description: {current_level["description"]}

The next level is:

Score: {next_score}
Title: {next_level["title"]}
Description: {next_level["description"]}

Your task:
Give exactly 3 specific improvements that would help this exact piece of writing move closer to the next level.

Rules:
- Focus on the learner's actual writing, not generic writing advice.
- Each improvement must include a specific phrase or sentence from the learner's writing.
- The "before" value must be copied from, or be a very close excerpt from, the learner's original writing.
- The "after" value must show a stronger version.
- Do not make the writing sound overly formal or unnatural.
- Keep the feedback encouraging and practical.
- Return only valid JSON.
- Do not include markdown.
- Return a JSON list directly, not an object.

Return exactly this structure:

[
    {{
        "title": "Use more precise descriptions",
        "explanation": "Your writing is clear, but some descriptions are general. More specific language would make the paragraph stronger.",
        "before": "The food was very good.",
        "after": "The food was flavorful and freshly prepared."
    }},
    {{
        "title": "Improve sentence flow",
        "explanation": "Some ideas could connect more smoothly. A small transition can make the writing feel more natural.",
        "before": "We ate dinner. We walked home.",
        "after": "After dinner, we walked home."
    }},
    {{
        "title": "Add more relevant detail",
        "explanation": "Your answer addresses the prompt, but adding one concrete detail would make it stronger.",
        "before": "I had a good time.",
        "after": "I had a good time because the conversation was relaxed and funny."
    }}
]
""".strip()

            model_attempts = [
                {"provider": "openai", "model": "gpt-4.1-mini"},
                {"provider": "openai", "model": "gpt-4.1-mini"},
                {"provider": "openai", "model": "gpt-4.1"},
                {"provider": "gemini", "model": "gemini-2.5-flash"},
                {"provider": "gemini", "model": "gemini-2.5-pro"}
            ]

            failures = []

            for model_attempt in model_attempts:
                try:
                    if model_attempt["provider"] == "openai":
                        bot = vitalib.Chatbot.OpenAI(model_attempt["model"])
                    else:
                        bot = vitalib.Chatbot.Gemini(model_attempt["model"])

                    response = bot.send_message(prompt)

                    improvements = json.loads(response)

                    if not isinstance(improvements, list):
                        raise ValueError(f"Improvements response was not a list: {response}")

                    if len(improvements) != 3:
                        raise ValueError(f"Expected exactly 3 improvements, got {len(improvements)}: {response}")

                    for item in improvements:
                        if not isinstance(item, dict):
                            raise ValueError(f"Improvement item was not an object: {item}")

                        required_keys = ["title", "explanation", "before", "after"]

                        for key in required_keys:
                            if key not in item:
                                raise ValueError(f"Missing key '{key}' in improvement item: {item}")

                            if not isinstance(item[key], str):
                                raise ValueError(f"Improvement key '{key}' was not a string: {item}")

                            if item[key].strip() == "":
                                raise ValueError(f"Improvement key '{key}' was empty: {item}")

                    return improvements

                except Exception as e:
                    failures.append({
                        "provider": model_attempt["provider"],
                        "model": model_attempt["model"],
                        "error": str(e)
                    })
                    time.sleep(1)

            raise ValueError(f"All improvements attempts failed: {failures}")

        def vocabulary(self, prompt_text, text):
            prompt = f"""
You are helping a language learner improve their writing in {self.language}.

The learner was given this writing prompt:

{prompt_text}

The learner wrote this response:

{text}

Your task:
Identify exactly 10 useful vocabulary words that could have made this specific writing stronger, more precise, or more natural.

Rules:
- Recommend words in {self.language}.
- Recommend useful words, not obscure or overly formal words.
- Do not recommend a word only because it sounds more advanced.
- Each word should improve precision, naturalness, or expressiveness.
- The "word" should be the base dictionary form of the word.
- The "before" value must be copied from, or be a very close excerpt from, the learner's original writing.
- The "after" value must show how the suggested word could improve that exact phrase or sentence.
- Return exactly 10 items.
- Return only valid JSON.
- Do not include markdown.
- Return a JSON list directly, not an object.

Return exactly this structure:

[
    {{
        "word": "flavorful",
        "language": "en",
        "explanation": "This word makes your description of the food more specific and natural.",
        "before": "The food was very good.",
        "after": "The food was flavorful and freshly prepared."
    }}
]
""".strip()

            model_attempts = [
                {"provider": "openai", "model": "gpt-4.1-mini"},
                {"provider": "openai", "model": "gpt-4.1-mini"},
                {"provider": "openai", "model": "gpt-4.1"},
                {"provider": "gemini", "model": "gemini-2.5-flash"},
                {"provider": "gemini", "model": "gemini-2.5-pro"}
            ]

            failures = []

            for model_attempt in model_attempts:
                try:
                    if model_attempt["provider"] == "openai":
                        bot = vitalib.Chatbot.OpenAI(model_attempt["model"])
                    else:
                        bot = vitalib.Chatbot.Gemini(model_attempt["model"])

                    response = bot.send_message(prompt)

                    vocabulary_words = json.loads(response)

                    if not isinstance(vocabulary_words, list):
                        raise ValueError(f"Vocabulary response was not a list: {response}")

                    if len(vocabulary_words) != 10:
                        raise ValueError(f"Expected exactly 10 vocabulary words, got {len(vocabulary_words)}: {response}")

                    for item in vocabulary_words:
                        if not isinstance(item, dict):
                            raise ValueError(f"Vocabulary item was not an object: {item}")

                        required_keys = ["word", "language", "explanation", "before", "after"]

                        for key in required_keys:
                            if key not in item:
                                raise ValueError(f"Missing key '{key}' in vocabulary item: {item}")

                            if not isinstance(item[key], str):
                                raise ValueError(f"Vocabulary key '{key}' was not a string: {item}")

                            if item[key].strip() == "":
                                raise ValueError(f"Vocabulary key '{key}' was empty: {item}")

                    edge_range = vitalib.Test.Get(
                        conn=self.conn,
                        user_id=self.user_id,
                        language=self.language
                    ).edge_range()

                    center = (edge_range[0] + edge_range[1]) / 2

                    enriched_words = []

                    for word in vocabulary_words:
                        lemma_info = vitalib.Database.Vocab.Get(
                            conn=self.conn,
                            user_id=self.user_id,
                            language=self.language
                        ).lemma_by_name(word["word"])

                        if not lemma_info:
                            continue

                        if lemma_info.get("rank") is None:
                            continue

                        word["lemma_id"] = lemma_info["lemma_id"]
                        word["rank"] = lemma_info["rank"]
                        word["definition"] = lemma_info["definition"]
                        word["distance_from_center"] = abs(lemma_info["rank"] - center)

                        enriched_words.append(word)

                    enriched_words.sort(key=lambda item: item["distance_from_center"])

                    top_three_words = enriched_words[:3]

                    for word in top_three_words:
                        word.pop("rank", None)
                        word.pop("distance_from_center", None)

                    if len(top_three_words) == 3:
                        return top_three_words

                    raise ValueError(f"Only found {len(top_three_words)} usable vocabulary words.")

                except Exception as e:
                    failures.append({
                        "provider": model_attempt["provider"],
                        "model": model_attempt["model"],
                        "error": str(e)
                    })
                    time.sleep(1)

            raise ValueError(f"All vocabulary attempts failed: {failures}")