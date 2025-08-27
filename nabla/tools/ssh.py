import os
import subprocess
import datetime
from subprocess import call

# See https://medium.com/@eren.c.uysal/optimizing-ssh-key-management-on-linux-servers-6a60949486fb
# os.system('ls -lrta')

cutoff = datetime.datetime.now() - datetime.timedelta(days=90)
print(f"Remove keys older than: {cutoff.isoformat()}")

call(
    'echo "Scans for public keys older than 90 days to flag for rotation."',
    shell=True,  # nosec B602
)
call(
    "find /home -name 'id_rsa.pub' -mtime +90 -exec echo \"Rotate key:\" {} \\;",  # nosec B602
    shell=True,
)

# Programmatically verifies that a private key exists and is readable by generating its public equivalent.
key_path = "~/.ssh/id_ed25519"
if os.path.exists(key_path):
    subprocess.run(["ssh-keygen", "-y", "-f", key_path], check=False)  # noqa: S603

call(
    'echo "Checks for duplicate or reused SSH public keys in authorized_keys."',  # nosec B602
    shell=True,
)
call("awk '{print $1, $2}' ~/.ssh/authorized_keys | sort | uniq -c", shell=True)  # nosec B602

call(
    'echo "Flags keys issued in the past based on embedded key comments or tags."',  # nosec B602
    shell=True,
)
call(
    "find /home/*/.ssh/authorized_keys -type f -exec grep -H '2023-' {} \\;",
    shell=True,  # nosec B602
)
