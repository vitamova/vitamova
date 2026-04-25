import psycopg2

filename = "lemmas_1096.txt"

#the password is in ~/data/db_pw.txt
db_password_path = "~/data/db_pw.txt"
with open(db_password_path, 'r') as f:
    db_password = f.read().strip()

conn = psycopg2.connect(
    host="localhost",
    database="vitamova",
    user="webapp",
    password=db_password
)

cursor = conn.cursor()

with open(filename, "r", encoding="utf-8") as file:
    lines = file.readlines()

# Start at line 8 based on your current script: lines[7:]
# Python indexes start at 0, so index 7 means the 8th line.
for line in lines[7:]:
    values = line.rstrip("\n").split("\t")

    rank = int(values[0])
    lemma = values[1]
    pos = values[2]

    cursor.execute(
        """
        INSERT INTO spanish_lemmas (rank, lemma, pos)
        VALUES (%s, %s, %s)
        """,
        (rank, lemma, pos)
    )

conn.commit()

cursor.close()
conn.close()

print("Done importing lemmas.")