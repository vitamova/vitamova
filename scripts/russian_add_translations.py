import json
import time
import psycopg2
from openai import OpenAI


DB_PASSWORD_PATH = "data/db_pw.txt"
OPENAI_KEY_PATH = "data/chatgpt_key.txt"

DB_HOST = "vitamova-db.cluster-cartvcorpihi.us-east-1.rds.amazonaws.com"
DB_NAME = "vitamova"
DB_USER = "webapp"

MODEL = "gpt-5-mini"
BATCH_SIZE = 100
SLEEP_BETWEEN_BATCHES_SECONDS = 0.5


def read_file(path):
    with open(path, "r") as f:
        return f.read().strip()


def get_openai_client():
    api_key = read_file(OPENAI_KEY_PATH)
    return OpenAI(api_key=api_key)


def get_db_connection():
    db_password = read_file(DB_PASSWORD_PATH)

    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=db_password
    )


def fetch_lemmas_to_process(cursor, limit):
    cursor.execute(
        """
        SELECT rank, lemma, pos
        FROM russian_lemmas
        WHERE translation IS ''
           OR definition IS ''
        ORDER BY rank ASC
        LIMIT %s;
        """,
        (limit,)
    )

    return cursor.fetchall()


def build_prompt(rows):
    items = []

    for rank, lemma, pos in rows:
        items.append({
            "rank": rank,
            "lemma": lemma,
            "pos": pos
        })

    return f"""
You are helping build a Russian vocabulary-learning app.

For each Russian lemma, provide:
1. "translation": a concise English translation.
2. "definition": a simple Russian definition written in Russian.

Rules:
- The definition must be in Russian.
- The translation should be in English.
- Use the part of speech to disambiguate the lemma.
- For translation, prefer one clear best English translation.
- Only include multiple translations if a single English word or phrase would be misleading or incomplete for a learner.
- If multiple translations are truly needed, separate them with comma+space, like: "to become, to turn into".
- Do not include near-synonyms just to be exhaustive.
- Do not include long explanations in the translation field.
- Keep definitions short and useful for language learners.
- Do not include examples unless necessary.
- Return only valid JSON.
- Return a JSON object with one key: "results".
- "results" must be an array.
- Each object inside "results" must include: rank, translation, definition.
- Do not omit any ranks.

Input lemmas:
{json.dumps(items, ensure_ascii=False)}
"""


def call_openai(client, rows):
    prompt = build_prompt(rows)

    response = client.responses.create(
        model=MODEL,
        input=prompt,
        text={
            "format": {
                "type": "json_schema",
                "name": "lemma_translations_and_definitions",
                "schema": {
                    "type": "object",
                    "properties": {
                        "results": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "rank": {
                                        "type": "integer"
                                    },
                                    "translation": {
                                        "type": "string"
                                    },
                                    "definition": {
                                        "type": "string"
                                    }
                                },
                                "required": ["rank", "translation", "definition"],
                                "additionalProperties": False
                            }
                        }
                    },
                    "required": ["results"],
                    "additionalProperties": False
                }
            }
        }
    )

    return json.loads(response.output_text)["results"]


def update_rows(cursor, results):
    for item in results:
        cursor.execute(
            """
            UPDATE russian_lemmas
            SET translation = %s,
                definition = %s
            WHERE rank = %s;
            """,
            (
                item["translation"],
                item["definition"],
                item["rank"]
            )
        )


def main():
    client = get_openai_client()
    conn = get_db_connection()
    cursor = conn.cursor()

    total_processed = 0

    try:
        while True:
            rows = fetch_lemmas_to_process(cursor, BATCH_SIZE)

            if not rows:
                print("Done. No remaining lemmas need translation/definition.")
                break

            print(f"Processing batch of {len(rows)} lemmas. Starting rank: {rows[0][0]}")

            try:
                results = call_openai(client, rows)

                expected_ranks = {row[0] for row in rows}
                returned_ranks = {item["rank"] for item in results}

                missing = expected_ranks - returned_ranks
                unexpected = returned_ranks - expected_ranks

                if missing:
                    raise ValueError(f"OpenAI response missing ranks: {sorted(missing)}")

                if unexpected:
                    raise ValueError(f"OpenAI response included unexpected ranks: {sorted(unexpected)}")

                update_rows(cursor, results)
                conn.commit()

                total_processed += len(results)
                print(f"Committed {len(results)} rows. Total processed: {total_processed}")

                time.sleep(SLEEP_BETWEEN_BATCHES_SECONDS)

            except Exception as e:
                conn.rollback()
                print("Error processing batch. Rolled back this batch.")
                print(e)
                break

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()