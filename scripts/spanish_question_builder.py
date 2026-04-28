import json
import random
import time
import traceback
import psycopg2

from openai import OpenAI


DB_PASSWORD_PATH = "data/db_pw.txt"
OPENAI_KEY_PATH = "data/chatgpt_key.txt"

DB_HOST = "vitamova-db.cluster-cartvcorpihi.us-east-1.rds.amazonaws.com"
DB_NAME = "vitamova"
DB_USER = "webapp"

MODEL = "gpt-5-mini"

TOTAL_QUESTIONS_TARGET = 1000
OPENAI_BATCH_SIZE = 5
MAX_RETRIES = 4
SLEEP_BETWEEN_OPENAI_CALLS = 0.5

LEVEL_RANGES = {
    1: (1, 1500),
    2: (1501, 3000),
    3: (3001, 6000),
    4: (6001, 10000),
    5: (10001, 15000),
    6: (15001, None),
}


def read_file(path):
    with open(path, "r") as f:
        return f.read().strip()


def get_db_connection():
    db_password = read_file(DB_PASSWORD_PATH)

    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=db_password,
    )


def get_openai_client():
    api_key = read_file(OPENAI_KEY_PATH)
    return OpenAI(api_key=api_key)


def get_level_targets(total_questions):
    base = total_questions // 6
    remainder = total_questions % 6

    targets = {}

    for level in range(1, 7):
        targets[level] = base

    # Spread the remainder across the lower levels.
    for level in range(1, remainder + 1):
        targets[level] += 1

    return targets


def get_existing_question_count_for_level(cursor, level):
    min_rank, max_rank = LEVEL_RANGES[level]

    if max_rank is None:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM spanish_vocab_test_bank
            WHERE lemma_rank >= %s
            """,
            [min_rank]
        )
    else:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM spanish_vocab_test_bank
            WHERE lemma_rank BETWEEN %s AND %s
            """,
            [min_rank, max_rank]
        )

    return cursor.fetchone()[0]


def fetch_lemmas_for_level(cursor, level, count):
    min_rank, max_rank = LEVEL_RANGES[level]

    if max_rank is None:
        cursor.execute(
            """
            SELECT sl.rank, sl.lemma, sl.pos, sl.translation, sl.definition
            FROM spanish_lemmas sl
            WHERE sl.rank >= %s
              AND NOT EXISTS (
                  SELECT 1
                  FROM spanish_vocab_test_bank q
                  WHERE q.lemma_rank = sl.rank
              )
              AND sl.translation IS NOT NULL
              AND sl.definition IS NOT NULL
            ORDER BY RANDOM()
            LIMIT %s
            """,
            [min_rank, count]
        )
    else:
        cursor.execute(
            """
            SELECT sl.rank, sl.lemma, sl.pos, sl.translation, sl.definition
            FROM spanish_lemmas sl
            WHERE sl.rank BETWEEN %s AND %s
              AND NOT EXISTS (
                  SELECT 1
                  FROM spanish_vocab_test_bank q
                  WHERE q.lemma_rank = sl.rank
              )
              AND sl.translation IS NOT NULL
              AND sl.definition IS NOT NULL
            ORDER BY RANDOM()
            LIMIT %s
            """,
            [min_rank, max_rank, count]
        )

    return cursor.fetchall()


def build_prompt(lemma_rows):
    input_items = []

    for rank, lemma, pos, translation, definition in lemma_rows:
        input_items.append({
            "lemma_rank": rank,
            "lemma": lemma,
            "part_of_speech": pos,
            "translation_en": translation,
            "definition_es": definition,
        })

    return f"""
You are creating multiple-choice Spanish vocabulary diagnostic questions.

For each Spanish lemma, create one fill-in-the-blank question entirely in Spanish.

Question style:
- The question must be a natural Spanish sentence with exactly one blank.
- Write the blank exactly as _____.
- The blank should test whether the learner understands how to use the target lemma in context.
- Use the lemma, part of speech, English translation, and Spanish definition to disambiguate meaning.
- The correct_answer must be the target Spanish lemma, or the most natural inflected form of it if the sentence requires inflection.
- The distractors must also be Spanish words or short Spanish phrases.
- Distractors should be plausible in the sentence structure but clearly wrong in meaning.
- Avoid distractors that are only spelling variants, gender variants, number variants, or near-identical synonyms of the correct answer.
- Avoid distractors that are obviously impossible only because of grammar.
- Keep the sentence short and clear.
- Prefer everyday, natural contexts.
- Do not include English anywhere in the question or answer options.
- Do not include the correct answer inside the question sentence.
- Return only valid JSON.

Output requirements:
- Return a JSON object with one key: "results".
- "results" must be an array.
- Return exactly one result for each input lemma.
- Each object inside "results" must include:
  - lemma_rank
  - question
  - correct_answer
  - distractor_1
  - distractor_2
  - distractor_3

Example:
Question: "No puedo salir porque tengo que _____ para el examen."
Correct answer: "estudiar"
Distractors: "cocinar", "romper", "vender"

Input lemmas:
{json.dumps(input_items, ensure_ascii=False)}
"""


def validate_generated_questions(results, expected_ranks):
    if not isinstance(results, list):
        raise ValueError("OpenAI response results was not a list.")

    required_fields = [
        "lemma_rank",
        "question",
        "correct_answer",
        "distractor_1",
        "distractor_2",
        "distractor_3",
    ]

    returned_ranks = set()

    for item in results:
        for field in required_fields:
            if field not in item:
                raise ValueError(f"Missing field: {field}")

            if item[field] is None or str(item[field]).strip() == "":
                raise ValueError(f"Empty field: {field}")

        lemma_rank = int(item["lemma_rank"])
        returned_ranks.add(lemma_rank)

        question = str(item["question"]).strip()

        if "_____" not in question:
            raise ValueError(f"Question for rank {lemma_rank} does not include _____.")

        if question.count("_____") != 1:
            raise ValueError(f"Question for rank {lemma_rank} does not have exactly one blank.")

        correct_answer = str(item["correct_answer"]).strip()

        if correct_answer.casefold() in question.casefold():
            raise ValueError(f"Question for rank {lemma_rank} appears to contain the correct answer.")

        options = [
            item["correct_answer"],
            item["distractor_1"],
            item["distractor_2"],
            item["distractor_3"],
        ]

        normalized_options = [
            str(option).strip().casefold()
            for option in options
        ]

        if len(set(normalized_options)) != 4:
            raise ValueError(f"Duplicate answer options for rank {lemma_rank}.")

    missing_ranks = expected_ranks - returned_ranks
    unexpected_ranks = returned_ranks - expected_ranks

    if missing_ranks:
        raise ValueError(f"Missing lemma ranks: {sorted(missing_ranks)}")

    if unexpected_ranks:
        raise ValueError(f"Unexpected lemma ranks: {sorted(unexpected_ranks)}")


def generate_questions_with_openai(client, lemma_rows):
    expected_ranks = {int(row[0]) for row in lemma_rows}
    prompt = build_prompt(lemma_rows)

    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.responses.create(
                model=MODEL,
                input=prompt,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "vocab_diagnostic_questions",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "results": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "lemma_rank": {"type": "integer"},
                                            "question": {"type": "string"},
                                            "correct_answer": {"type": "string"},
                                            "distractor_1": {"type": "string"},
                                            "distractor_2": {"type": "string"},
                                            "distractor_3": {"type": "string"},
                                        },
                                        "required": [
                                            "lemma_rank",
                                            "question",
                                            "correct_answer",
                                            "distractor_1",
                                            "distractor_2",
                                            "distractor_3",
                                        ],
                                        "additionalProperties": False,
                                    },
                                }
                            },
                            "required": ["results"],
                            "additionalProperties": False,
                        },
                    }
                },
            )

            parsed = json.loads(response.output_text)
            results = parsed["results"]

            validate_generated_questions(results, expected_ranks)

            return results

        except Exception as e:
            last_error = e

            print(f"\nOpenAI generation failed. Attempt {attempt}/{MAX_RETRIES}")
            print("Error type:", type(e).__name__)
            print("Error:", e)
            traceback.print_exc()

            if attempt < MAX_RETRIES:
                sleep_seconds = (2 ** (attempt - 1)) + random.uniform(0, 0.75)
                print(f"Retrying in {sleep_seconds:.2f} seconds...")
                time.sleep(sleep_seconds)

    raise last_error


def insert_questions(cursor, generated_questions):
    inserted_count = 0

    for item in generated_questions:
        cursor.execute(
            """
            INSERT INTO spanish_vocab_test_bank (
                lemma_rank,
                question,
                correct_answer,
                distractor_1,
                distractor_2,
                distractor_3
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            [
                item["lemma_rank"],
                item["question"],
                item["correct_answer"],
                item["distractor_1"],
                item["distractor_2"],
                item["distractor_3"],
            ]
        )

        inserted_count += 1

    return inserted_count


def chunk_list(items, chunk_size):
    for i in range(0, len(items), chunk_size):
        yield items[i:i + chunk_size]


def main():
    client = get_openai_client()
    conn = get_db_connection()
    cursor = conn.cursor()

    targets = get_level_targets(TOTAL_QUESTIONS_TARGET)

    print("Question generation target:")
    for level, target in targets.items():
        print(f"  Level {level}: {target}")

    total_inserted = 0

    try:
        for level in range(1, 7):
            target_for_level = targets[level]
            existing_count = get_existing_question_count_for_level(cursor, level)
            remaining_for_level = max(target_for_level - existing_count, 0)

            print("\n----------------------------------------")
            print(f"Level {level}")
            print(f"Target: {target_for_level}")
            print(f"Existing questions: {existing_count}")
            print(f"Need to generate: {remaining_for_level}")

            if remaining_for_level == 0:
                continue

            lemma_rows = fetch_lemmas_for_level(
                cursor=cursor,
                level=level,
                count=remaining_for_level
            )

            if not lemma_rows:
                print(f"No eligible lemmas found for level {level}. Skipping.")
                continue

            print(f"Fetched {len(lemma_rows)} lemmas for level {level}.")

            for batch_number, lemma_batch in enumerate(chunk_list(lemma_rows, OPENAI_BATCH_SIZE), start=1):
                print(
                    f"Level {level}, batch {batch_number}: "
                    f"generating {len(lemma_batch)} questions..."
                )

                try:
                    generated_questions = generate_questions_with_openai(client, lemma_batch)

                    inserted_count = insert_questions(cursor, generated_questions)
                    conn.commit()

                    total_inserted += inserted_count

                    print(
                        f"Committed {inserted_count} questions. "
                        f"Total inserted this run: {total_inserted}"
                    )

                    time.sleep(SLEEP_BETWEEN_OPENAI_CALLS)

                except Exception as e:
                    conn.rollback()

                    print("\nFailed to generate/insert this batch. Rolled back this batch only.")
                    print("Continuing to next batch.")
                    print("Error:", e)
                    traceback.print_exc()

                    continue

        print("\nDone.")
        print(f"Total inserted this run: {total_inserted}")

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()