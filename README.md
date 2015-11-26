# WPM-to-Zabbix
Funnel WPM data to Zabbix.

Will match WPM Monitor description to a Zabbix item key on the Zabbix host specified in the config.
If description is empty on WPM Monitor, will skip.

I currently run this on a cron job every 5 minutes.

## Setup
Rename config.ini.example to config.ini and fill in information.

Will create SQLite db in ```db``` dir to track changes.

## Config
* WPM
  * api_key
  * api_secret
  * sample_delta_min (how far back to request data from (last ```x``` minutes))
* Zabbix Server (refers to Zabbix SERVER, not a monitored host)
  * ip
  * port

* Zabbix Host (refers to a host monitored within Zabbix)
  * host_name

## Requires:
* tfullert/wpm-api (included)
* python-protobix
* Requests
* SimpleJSON
* psutil
* pytz
* sqlite3

## Disclaimer:
* Not affiliated with Neustar nor endorsed.
* Writing log to /var/log requires root currently.

## TODO:
* Learn better python syntax and code style :D
* Create db dir if not exist
* Manage db size and delete at defined threshold.
* Improve and clean up logging
