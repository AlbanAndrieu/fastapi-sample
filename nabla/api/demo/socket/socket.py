import socket

from nabla.config_settings import APP_DOMAIN


def check_internet():
    try:
        socket.create_connection(("www.google.com", 80))
        print("Internet connection is available.")
    except OSError:
        print("No Internet connection.")


def get_dns_info():
    socket.setdefaulttimeout(5)  # Set a timeout for DNS queries
    dns_info = socket.getaddrinfo(APP_DOMAIN, None)
    for info in dns_info:
        print(info)


try:
    check_internet()
    get_dns_info()

    ip_address = socket.gethostbyname(APP_DOMAIN)
    print(f"The IP address of {APP_DOMAIN} is {ip_address}")

except socket.gaierror as e:
    print(f"Error: {e}")
