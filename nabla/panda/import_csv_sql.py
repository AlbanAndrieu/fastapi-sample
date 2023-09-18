import datetime

import pandas as pd
import psycopg2
from sqlalchemy import create_engine

# Database connection parameters
db_params = {
    "database": "analyticsprocessordev",
    "user": "analyticsprocessor",
    "password": "analyticsprocessorpass",
    "host": "10.30.10.70",  # Change this to your PostgreSQL server host
    "port": "5432",  # Change this to your PostgreSQL server port
}

# PostgreSQL table name
table_name = "connected_users"


# async def create_db_connection_pool() -> psycopg2.pool.ThreadedConnectionPool:
#     """Create a session as a dependency"""
#     settings = get_settings()

#     return await psycopg2.connect(
#         host=settings.db_host,
#         port=settings.db_port,
#         database=settings.db_name,
#         user=settings.db_user,
#         password=settings.db_password,
#     )

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


def import_logs_from_csv(csv_file_path: str):
    try:
        """Connect to the PostgreSQL database"""
        # conn = create_db_connection_pool()
        conn = psycopg2.connect(**db_params)

        # Create a cursor object
        cur = conn.cursor()

        # raw_copy_statement(csv_file_path, cur)
        # Create an SQLAlchemy engine
        engine = create_engine(
            f'postgresql://{db_params["user"]}:{db_params["password"]}@{db_params["host"]}:{db_params["port"]}/{db_params["database"]}'
        )

        print(f"Connected to PostgreSQL database {db_params['database']}")

        # Read the CSV file into a Pandas DataFrame
        # col_names = ["user_id", "email", "last_login", "cgu_read_and_accepted", "roles", ...]
        col_names = ["user_id", "email", "last_login", "cgu_read_and_accepted", "roles"]
        df = pd.read_csv(
            csv_file_path,
            names=col_names,
            sep=",",
            encoding="utf-8",
            skiprows=0,
            low_memory=False,
            lineterminator="\n",
            on_bad_lines="skip",
        )
        # quoting=csv.QUOTE_NONE, quotechar='"', delimiter=',', header=None

        # Add a new column with the current datetime
        df["process_date"] = datetime.datetime.now()

        print(df)

        # Insert the data into the PostgreSQL table
        df.to_sql(table_name, engine, if_exists="replace", index=True)

        # Commit the transaction
        conn.commit()
        print(f"Data from {csv_file_path} inserted into {table_name} successfully.")

        # Close the cursor and connection objects
        cur.close()

    except psycopg2.Error as error:
        print(f"psycopg2 Error: {error}")

    except Exception as e:
        print(e)
        print("Failed to import data from csv")

    finally:
        # Close the database connection
        if conn:
            conn.close()
