#!/bin/bash
set -xv
# See https://www.tools4noobs.com/online_php_functions/long2ip/
echo "127.0.0.1 2130706433"

echo "10.10.0.7 168427527"

# -- Check the activity log
# select *
# from security.access_log
# where ip=2130706433
# order by timestamp desc
# LIMIT 100;

#-- Insert it into the white listed table, replace stuff surrounded by "<>"
# INSERT INTO security.ip_granted_bypass(id, ip, "granted_at", comment)
# VALUES (
# 	(select nextval('security.ip_granted_bypass_id_seq')),
# 	2130706433,
# 	'now',
# 	'["albandrieu / User ID: null / IP: 127.0.0.1 (ip2long: 2130706433)"]'
# );
# INSERT INTO security.ip_granted_bypass(id, ip, "granted_at", comment)
# VALUES (
# 	(select nextval('security.ip_granted_bypass_id_seq')),
# 	168427527,
# 	'now',
# 	'["albandrieu / User ID: null / IP: 10.10.0.7 (ip2long: 168427527)"]'
# );
#
# TRUNCATE security.access_log;
# TRUNCATE security.ip_banned;
# TRUNCATE security.ip_warned;
# TRUNCATE security.user_warned;
# TRUNCATE security.user_banned;
# TRUNCATE back_action_log;

# podman run --rm -ti redis:7.0 redis-cli -h redis.service.gra.dev.consul FLUSHALL

# select * from users.key_customer where type='LAWFIRM' and status='CLIENT' and enabled is true limit 1;

# update users.key_customer set ip_addresses = '[{"ip":2130706433,"office":""},{"ip":2886991877,"office":""},{"ip": 2886991873,"office":""},{"ip": 168427527, "office": ""},{"ip": 168427707, "office": ""},{"ip": 1343161577, "office": ""}]'
# where id in (56, 247);

exit 0
