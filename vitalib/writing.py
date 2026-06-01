import json
import re
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
        def __init__(self, user_id, language):
            self.user_id = user_id
            self.language = language

        def score(self, prompt_text, text):
            model_rounds = [
                {
                    "openai": "gpt-4.1-mini",
                    "gemini": "gemini-2.5-flash"
                },
                {
                    "openai": "gpt-4.1",
                    "gemini": "gemini-2.5-pro"
                },
                {
                    "openai": "gpt-4o",
                    "gemini": "gemini-1.5-pro"
                }
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

1 - Unintelligible:
The intended meaning cannot be reliably determined, or the response is completely unrelated to the prompt.

2 - Mostly Unintelligible:
Some isolated ideas are understandable, but most of the message is unclear. The response may barely address the prompt or may be mostly off-topic.

3 - Difficult to Understand:
The general topic can be inferred, but understanding requires substantial effort. The response may address the prompt only partially or unclearly.

4 - Understandable with Significant Effort:
Most of the message can be understood, but frequent errors and awkward phrasing slow the reader down. The response should at least make a clear attempt to answer the prompt.

5 - Understandable:
The message is generally clear. Errors are common but rarely prevent understanding. The response answers the prompt in a basic but recognizable way.

6 - Comfortable:
The writing communicates effectively. Errors and awkward phrasing are noticeable but not distracting. The response answers the prompt clearly and includes some relevant detail.

7 - Strong:
The writing is clear, organized, and mostly natural. Minor issues do not interfere with communication. The response answers the prompt directly and develops the answer with relevant supporting details.

8 - Advanced:
The writing communicates complex or detailed ideas clearly and naturally. Few noticeable weaknesses. The response fully answers the prompt and develops the topic well.

9 - Near-Native:
The writing feels natural and sophisticated. Most educated native speakers would not immediately suspect the writer is a learner. The response fully answers the prompt with nuance, detail, and strong control of tone.

10 - Expert:
The writing demonstrates exceptional command of language, style, nuance, and audience awareness. The response answers the prompt completely and would be considered excellent by highly educated native speakers.

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

            for model_pair in model_rounds:
                openai_bot = vitalib.Chatbot.OpenAI(model_pair["openai"])
                openai_response = openai_bot.send_message(prompt)

                try:
                    openai_data = json.loads(openai_response)
                    openai_score = int(openai_data["score"])
                except Exception:
                    match = re.search(r"\b(10|[1-9])\b", openai_response)
                    if not match:
                        raise ValueError(f"Could not extract score from OpenAI response: {openai_response}")
                    openai_score = int(match.group(1))

                if openai_score < 1 or openai_score > 10:
                    raise ValueError(f"OpenAI score out of range: {openai_score}")

                gemini_bot = vitalib.Chatbot.Gemini(model_pair["gemini"])
                gemini_response = gemini_bot.send_message(prompt)

                try:
                    gemini_data = json.loads(gemini_response)
                    gemini_score = int(gemini_data["score"])
                except Exception:
                    match = re.search(r"\b(10|[1-9])\b", gemini_response)
                    if not match:
                        raise ValueError(f"Could not extract score from Gemini response: {gemini_response}")
                    gemini_score = int(match.group(1))

                if gemini_score < 1 or gemini_score > 10:
                    raise ValueError(f"Gemini score out of range: {gemini_score}")

                scores.append(openai_score)
                scores.append(gemini_score)

                model_results.append({
                    "provider": "openai",
                    "model": model_pair["openai"],
                    "score": openai_score
                })

                model_results.append({
                    "provider": "gemini",
                    "model": model_pair["gemini"],
                    "score": gemini_score
                })

                if abs(openai_score - gemini_score) <= 1:
                    return {
                        "status": "success",
                        "score": min(openai_score, gemini_score),
                        "method": "two_model_agreement",
                        "model_results": model_results
                    }

                counts = Counter(scores)
                highest_count = max(counts.values())

                if highest_count > 1:
                    tied_scores = [
                        score for score, count in counts.items()
                        if count == highest_count
                    ]

                    return {
                        "status": "success",
                        "score": min(tied_scores),
                        "method": "majority_vote",
                        "model_results": model_results
                    }

            return {
                "score": min(scores),
                "title": WRITING_SCORE_LEVELS[min(scores)]["title"],
                "description": WRITING_SCORE_LEVELS[min(scores)]["description"]
            }