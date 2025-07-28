import datetime
import os
import traceback
import urllib.request

# from typing import Sets
import pandas as pd
import psycopg2
from sqlalchemy import create_engine, text

from nabla.config_settings import get_settings
from nabla.utils.logger import logger

# Database connection parameters
# Dictionaries
db_params = {
    "database": "notes",
    "user": "fastapisample",
    "password": "password-reset-XXX",
    "host": "127.0.0.1",  # Change this to your PostgreSQL server host
    "port": "5432",  # Change this to your PostgreSQL server port
}

# PostgreSQL table name
table_name = "notes"

dest_folder = os.environ.get("dest_folder")

url = "https://raw.githubusercontent.com/aalbanandrieu/datasets/master/test.csv"
destination_path = f"{dest_folder}/test.csv"


# def raw_copy_statement(csv_file_path: str, cur: psycopg2.cursor):
#     with open(csv_file_path, "r", encoding="utf-8") as csv_file:

#         # Read the header row
#         header = csv_file.readline()

#         # Split the header row into a list of column names
#         column_names = header.strip().split(",")

#         # Create a COPY statement to insert the CSV data into the PostgreSQL table
#         copy_statement = "COPY {} ({}) FROM STDIN WITH CSV HEADER;".format(
#             table_name, ",".join(column_names)
#         )

#         # Execute the COPY statement
#         cur.copy_expert(copy_statement, csv_file)


def get_database_params() -> dict:
    settings = get_settings()

    # for k, v in db_params.items():
    #     print(k, v)

    try:
        # db_params['host']=getattr(settings, "db_host"),
        db_params["host"] = settings.db_host
        db_params["port"] = str(settings.db_port)
        db_params["database"] = settings.db_name
        db_params["user"] = settings.db_user
        db_params["password"] = settings.db_password
    except AttributeError as e:
        logger.error("Elements from the configuration settings are missing")
        raise AttributeError(f"ENV information is missing from the settings: {e}")

    # for k, v in db_params.items():
    #     print(k, v)
    return db_params


def showTitle(engine):
    with engine.connect() as connection:
        result = connection.execute(text("select title from notes"))
        for row in result:
            print("title:", row.title)


def download_file_from_url(url: str, dest_folder: str):
    """
    Download a file from a specific URL and download to the local directory
    """
    if not os.path.exists(str(dest_folder)):
        os.makedirs(str(dest_folder))  # create folder if it does not exist

    try:
        urllib.request.urlretrieve(url, destination_path)  # noqa # nosec
        logger.info("csv file downloaded successfully to the working directory")
    except Exception as e:
        logger.error(f"Error while downloading the csv file due to: {e}")
        traceback.print_exc()


def create_postgres_table(cur):
    """
    Create the Postgres table with a desired schema
    """
    try:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS notes (
        id serial NOT NULL PRIMARY KEY,
        title text NOT NULL,
        description text DEFAULT '',
        completed text DEFAULT 'False',
        process_date timestamp without time zone NOT NULL)""",
        )

        logger.info(
            " New table notes created successfully to postgres server",
        )
    except Exception as e:
        logger.error(f"Check if the table notes exists: {e}")
        traceback.print_exc()


def import_logs_from_csv(csv_file_path: str):
    get_database_params()

    # print(db_params)

    logger.info(
        f"Connected to PostgreSQL database {db_params['database']} on port {db_params['port']} with user {db_params['user']}",
    )

    try:
        # Create a cursor object
        # cur = conn.cursor()

        # Create an SQLAlchemy engine
        engine = create_engine(
            f'postgresql://{db_params["user"]}:{db_params["password"]}@{db_params["host"]}:{db_params["port"]}/{db_params["database"]}',
        )

        print(f"Connected to PostgreSQL database {db_params['database']}")

        # showTitle(engine)

        # See https://medium.com/@dogukannulu/data-engineering-end-to-end-project-postgresql-airflow-docker-pandas-91c6aa529030
        # for more automation

        # CREATE TABLE notes (
        # id serial NOT NULL PRIMARY KEY,
        # title text NOT NULL,
        # description text DEFAULT '',
        # completed text DEFAULT 'False',
        # process_date timestamp without time zone NOT NULL
        # )

        # DELETE FROM notes

        # Read the CSV file into a Pandas DataFrame
        col_names = ["title", "description", "completed", "created_date"]

        col_dtype = {
            # "user_id": "Int64",  # Use Int64 instead of int64 to handle missing values
            "title": "string",
            "description": "string",
            "completed": "string",
            "created_date": "datetime64[ns]", # datetime64[ns]
        }

        DATE_FORMAT = "mixed"  # %Y-%d-%m %H:%M:%S

        df = pd.read_csv(
            csv_file_path,
            names=col_names,
            dtype=col_dtype,
            sep=",",
            encoding="utf-8",
            skiprows=0,
            low_memory=False,
            # lineterminator="\n",
            on_bad_lines="skip",
            parse_dates=["created_date"],
            date_format=DATE_FORMAT,
            # header=None,
            header=0,
        )

        # SELECT pg_catalog.setval(
        # 'notes_id_seq',
        # (SELECT max(id) FROM notes),
        # true
        # );

        get_seq_id_sql = """
            SELECT pg_catalog.setval(
            'notes_id_seq',
            (SELECT max(id) FROM notes),
            true
            ) as id;
        """

        s_id = pd.read_sql(get_seq_id_sql, engine)

        print(s_id)

        # df.index = s_id["id"].values
        # df.index.name = "id"

        # quoting=csv.QUOTE_NONE, quotechar='"', delimiter=',', header=None
        # skipfooter=4,
        # skiprows=10,

        # df.set_index('id')
        # df.set_index("id", inplace=True)
        # df.rename_axis('id')

        # df.drop("cgu_read_and_accepted", axis=1, inplace=True)

        # Add a new column with the current datetime
        process_date = datetime.date(2024, 3, 29)
        print(process_date)
        # df["process_date"] = datetime.datetime.now()
        # Convert the created_date column to a datetime object

        # df['created_date'] = pd.to_datetime(df['created_date'], format='mixed', utc=True)
        df["created_date"] = pd.to_datetime(
            df["created_date"], format=DATE_FORMAT, utc=False,
        )

        print(df.info())

        print(df)

        print(df.dtypes)

        # Insert the data into the PostgreSQL table
        # df.to_sql(table_name, engine, if_exists="append", index=True, index_label="id")
        # Remove index when appending data to table with already existing data
        df.to_sql(table_name, engine, if_exists="append", index=False)

        # Commit the transaction
        # conn.commit()
        print(f"Data from {csv_file_path} inserted into {table_name} successfully.")

        # Close the cursor and connection objects
        # cur.close()

    except psycopg2.Error as error:
        print(f"psycopg2 Error: {error}")

    except Exception as e:
        print(e)
        print("Failed to import data from csv")

    # finally:
    #     # Close the database connection
    #     if conn:
    #         conn.close()
