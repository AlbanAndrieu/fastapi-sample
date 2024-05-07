import os

# pylint: disable=all
from influxdb_client import InfluxDBClient, Point, WriteOptions

# from influxdb_client import InfluxDBClient, Point, WritePrecision
from requests import get

# See https://dganais.medium.com/getting-started-with-python-and-influxdb-v2-0-f22e5175aba5

# Define Loki and InfluxDB configuration
loki_url = "http://loki.service.gra.dev.consul:3100"
# loki_url = "http://loki.service.gra.uat.consul:3100"
influxdb_url = (
    "http://influxdb.service.gra.dev.consul:8086"  # Replace with your InfluxDB endpoint
)
influxdb_token = os.environ.get("INFLUXDB_TOKEN")
influxdb_org = "test"  # Replace with your InfluxDB organization
influxdb_bucket = "my-loki"  # Replace with your InfluxDB bucket

# Initialize the InfluxDB client
client = InfluxDBClient(url=influxdb_url, token=influxdb_token, org=influxdb_org)

# from(bucket: "my-loki")
#   |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
#   |> filter(fn: (r) => r["_measurement"] == "log_data")
#   |> filter(fn: (r) => r["_field"] == "duration")
#   |> derivative(unit: 1s, nonNegative: false)
#   |> yield(name: "derivative")


# Function to query Loki for logs and import into InfluxDB
def import_logs_from_loki():
    # Define Loki query parameters (adjust as needed)
    loki_query = '{nomad_job="fastapi-sample"}'  # Replace with your Loki query
    # http://loki.service.gra.dev.consul:3100/loki/api/v1/query_range?query={nomad_job=%22fastapi-sample%22}&start=2023-09-13T00:00:00Z&end=2023-09-15T00:00:00Z
    start_time = "2023-09-12T00:00:00Z"  # Replace with your desired start time
    end_time = "2023-09-15T00:00:00Z"  # Replace with your desired end time

    # Build the Loki query URL
    loki_query_url = f"{loki_url}/loki/api/v1/query_range?query={loki_query}&start={start_time}&end={end_time}"
    print(f"Loki query URL: {loki_query_url}")

    # Retrieve logs from Loki
    response = get(loki_query_url)
    print(f"Response status code: {response.status_code}")
    if response.status_code == 200:
        data = response.json()["data"]["result"]

        # Write logs to InfluxDB
        with client.write_api(write_options=WriteOptions(batch_size=500)) as write_api:
            for log_entry in data:
                print(f"Values {log_entry['values']}.")
                # print(f"Values {log_entry['values'][1]}.")
                log_timestamp = str(log_entry["values"][1])
                # log_timestamp = int(float(str(log_entry["values"][1]))) * 1000000000  # Convert Loki timestamp to nanoseconds
                print(f"log_timestamp {log_timestamp}")
                log_message = str(log_entry["values"][2])
                point = (
                    Point("log_data")
                    .time(int(log_timestamp))
                    .field("message", log_message)
                )
                write_api.write(bucket=influxdb_bucket, record=point)

        print(f"Imported {len(data)} log entries into InfluxDB.")
    else:
        print("Failed to retrieve logs from Loki.")


if __name__ == "__main__":
    import_logs_from_loki()

# token = os.environ.get("INFLUXDB_TOKEN")
# org = "test"
# url = "http://influxdb.service.gra.dev.consul"

# write_client = influxdb_client.InfluxDBClient(url=url, token=token, org=org)

# bucket = "my-loki"

# write_api = write_client.write_api(write_options=SYNCHRONOUS)

# for value in range(5):
#     point = Point("measurement1").tag("tagname1", "tagvalue1").field("field1", value)
#     write_api.write(bucket=bucket, org="test", record=point)
#     time.sleep(1)  # separate points by 1 second
