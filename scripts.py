import sys

from nabla.panda.import_csv_sql import import_logs_from_csv

# from nabla.config_settings import get_settings

# settings = get_settings()

"""Usage : python3 scripts.py ~/Downloads/Product_activity_1.csv"""
if __name__ == "__main__":
    import_logs_from_csv(csv_file_path=sys.argv[1])
