import psycopg2

filename = "russian_lemmas.txt"

# The password is in data/db_pw.txt
db_password_path = "data/db_pw.txt"
with open(db_password_path, "r") as f:
    db_password = f.read().strip()

conn = psycopg2.connect(
    host="vitamova-db.cluster-cartvcorpihi.us-east-1.rds.amazonaws.com",
    database="vitamova",
    user="webapp",
    password=db_password
)

cursor = conn.cursor()

with open(filename, "r", encoding="utf-8") as file:
    lines = file.readlines()

# Adjust this if your Russian file has a different number of header lines.
# If there is no header, change this to lines.
for line in lines:
    line = line.strip()

    if not line:
        continue

    values = line.split()

    # Expected format:
    # rank frequency lemma pos
    if len(values) < 4:
        print(f"Skipping malformed line: {line}")
        continue

    rank = int(values[0])
    lemma = values[2]
    pos = values[3]

    cursor.execute(
        """
        INSERT INTO russian_lemmas (rank, lemma, pos)
        VALUES (%s, %s, %s)
        ON CONFLICT (rank) DO UPDATE
        SET lemma = EXCLUDED.lemma,
            pos = EXCLUDED.pos
        """,
        (rank, lemma, pos)
    )

conn.commit()

cursor.close()
conn.close()

print("Done importing Russian lemmas.")