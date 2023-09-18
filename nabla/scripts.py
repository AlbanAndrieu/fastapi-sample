import sys

from panda.import_csv_sql import import_logs_from_csv

"""Usage : python3 import_csv_sql.py ~/Downloads/Product\ activity.csv"""
if __name__ == "__main__":
    import_logs_from_csv(csv_file_path=sys.argv[1])
