import psycopg2

LEVEL_RANGES = {
    "1": (1, 1500),
    "2": (1501, 3000),
    "3": (3001, 6000),
    "4": (6001, 10000),
    "5": (10001, 15000),
    "6": (15001, None),
}

def get_level_choice():
    print("Select a difficulty level:")
    print("1: 0–1,500 most frequent words")
    print("2: 1,500–3,000 most frequent words")
    print("3: 3,000–6,000 most frequent words")
    print("4: 6,000–10,000 most frequent words")
    print("5: 10,000–15,000 most frequent words")
    print("6: 15,000+ most frequent words")

    while True:
        choice = input("Enter level 1-6: ").strip()

        if choice in LEVEL_RANGES:
            return choice

        print("Invalid choice. Please enter a number from 1 to 6.")


def main():
    filename = None  # not used, but left out intentionally since this reads from Postgres

    #the password is in data/db_pw.txt
    db_password_path = "data/db_pw.txt"
    with open(db_password_path, 'r') as f:
        db_password = f.read().strip()

    conn = psycopg2.connect(
        host="vitamova-db.cluster-cartvcorpihi.us-east-1.rds.amazonaws.com",
        database="vitamova",
        user="webapp",
        password=db_password
    )

    cursor = conn.cursor()

    level = get_level_choice()
    min_rank, max_rank = LEVEL_RANGES[level]

    if max_rank is None:
        cursor.execute(
            """
            SELECT lemma
            FROM spanish_lemmas
            WHERE rank >= %s
            ORDER BY RANDOM()
            LIMIT 10;
            """,
            (min_rank,)
        )
    else:
        cursor.execute(
            """
            SELECT lemma
            FROM spanish_lemmas
            WHERE rank BETWEEN %s AND %s
            ORDER BY RANDOM()
            LIMIT 10;
            """,
            (min_rank, max_rank)
        )

    words = cursor.fetchall()

    cursor.close()
    conn.close()

    print("\nRandom words:")
    for word in words:
        print(word[0])


if __name__ == "__main__":
    main()