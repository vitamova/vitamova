import psycopg2
from concurrent.futures import ThreadPoolExecutor, TimeoutError

class Status:
    def __init__(self, conn_params):
        self.conn_params = conn_params

    def get(self):
        def quick_check():
            conn = psycopg2.connect(
                **self.conn_params,
                connect_timeout=1
            )

            try:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1;")
                    result = cursor.fetchone()

                return result is not None and result[0] == 1

            finally:
                conn.close()

        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(quick_check)
                return future.result(timeout=0.5)

        except TimeoutError:
            return False

        except Exception:
            return False

    def start(self):
        try:
            conn = psycopg2.connect(
                **self.conn_params,
                connect_timeout=15
            )

            try:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1;")
                    result = cursor.fetchone()

                if result is not None and result[0] == 1:
                    return {
                        "status": "ok",
                        "message": "Database start successful."
                    }

                return {
                    "status": "error",
                    "error": "Database did not return the expected response."
                }

            finally:
                conn.close()

        except Exception as error:
            return {
                "status": "error",
                "error": str(error)
            }