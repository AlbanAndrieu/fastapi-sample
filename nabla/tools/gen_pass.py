import getpass

import bcrypt

password = getpass.getpass("password: ")
hashed_password = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
print(hashed_password.decode())

# python3 gen_pass.py
# python3 ./nabla/tools/gen_pass.py
