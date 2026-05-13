import vitalib

class Test:
    def __init__(self, conn):
        self.conn = conn
    def grade(self, answers):
        # This just returns right or wrong for each question
        return answers
    # This will get questions based on: diagnostic, frontier, and batch
    # Batch is an optional parameter
    def get_questions(self, type, score, batch=None):
        # Get frontier based on score
        frontier = min((score // 1000) + 1, 6)
        fetch_counts = {}
        if type == "diagnostic":
            # Batch must be provided for diagnostic questions
            if batch is None:
                raise ValueError("Batch must be provided for diagnostic questions")
            # If batch is 1, fetch_counts should be 3 each
            if batch == 1:
                fetch_counts = {i: 3 for i in range(1, 7)}
            # If batch is anything else fetch_counts should be based on frontier
        if type == "vocab_builder":
            # Get 8 questions from the frontier level 1 from a level above and 1 from a level below
            # If frontier is 1 do an 8/2 split
            # If frontier is 6 do a 8/2 split but with the below level instead of the above level
            if frontier == 1:
                fetch_counts[1] = 8
                fetch_counts[2] = 2
            elif frontier == 6:
                fetch_counts[5] = 2
                fetch_counts[6] = 8
            else:
                fetch_counts[frontier - 1] = 1
                fetch_counts[frontier] = 8
                fetch_counts[frontier + 1] = 1
        # Fetch questions based on fetch_counts
        questions = vitalib.Database.Test(self.conn).fetch_questions(fetch_counts)
        return questions