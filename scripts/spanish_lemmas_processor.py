# Change this to the file you want to process
filename = "lemmas_1096.txt"

with open(filename, "r", encoding="utf-8") as file:
    lines = file.readlines()

# Lines 7-16 are indexes 6-15 in Python
for line in lines[6:16]:
    values = line.rstrip("\n").split("\t")
    print(values)