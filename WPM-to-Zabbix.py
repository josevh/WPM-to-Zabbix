#!/usr/bin/env python

import sys, os
from lib.wpm_api.client import Client
from lib.wpm_api.monitor import Monitor
import json                 #decode request object returned by wpm-api lib
import time                 #get time for PAUSE, time.sleep
import datetime             #get time for sample params; startDate and endDate
import protobix             #for python-zabbix_sender
import logging              #for logging
import logging.handlers	    #for logging
import sqlite3              #for db
import ConfigParser         #for reading config

''' set up logging '''
LOG_FILENAME = '/var/log/wpm/wpm-to-zabbix.log'	                                # TODO: create dir if not exist
my_logger = logging.getLogger('MainLog')
my_logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler = logging.handlers.RotatingFileHandler(
                LOG_FILENAME, maxBytes=5000000, backupCount=5) #5MB
handler.setFormatter(formatter)
my_logger.addHandler(handler)

stdout_logger = logging.StreamHandler(sys.stdout)
stdout_logger.setLevel(logging.DEBUG)
stdout_logger.setFormatter(formatter)
#my_logger.addHandler(stdout_logger)

stderr_logger = logging.StreamHandler(sys.stderr)
stderr_logger.setLevel(logging.DEBUG)
stderr_logger.setFormatter(formatter)
my_logger.addHandler(stderr_logger)

def printMonitorsDB(step):
    cur = conn.cursor()
    cur.execute('''
    select * from monitors
    ''')
    for row in cur.fetchall():
        print step
        print row

dir = os.path.dirname(__file__)
my_logger.debug('dir:' + dir)

''' read config file '''
my_logger.debug('Check config file')
config = ConfigParser.ConfigParser()                                            # TODO: catch if not exist
config.read(os.path.join(dir, 'config.ini'))

''' set up db '''
my_logger.debug('Check DB')
db_filename = os.path.join(dir, 'db/monitors.db')
schema_filename = os.path.join(dir, 'db/schema.sql')
db_is_new = not os.path.exists(db_filename)
with sqlite3.connect(db_filename) as conn:
    if db_is_new:
        my_logger.debug('Creating schema')
        with open(schema_filename, 'rt') as f:
            schema = f.read()
        conn.executescript(schema)
        conn.commit()

    else:
        my_logger.debug('Database exists, assume schema does, too.')
        pass

def isNewSampleDB(monitor_id, sample_id):
    cur = conn.cursor()
    cur.execute('''
    select * from monitors where monitor_id=? and last_sample_id=?
    ''', (monitor_id, sample_id))
    if len(cur.fetchall()) > 0:
        return False
    else:
        return True

def updateSampleDB(monitor_id, sample_id):
    cur = conn.cursor()
    cur.execute('''
    select * from monitors where monitor_id=?
    ''', (monitor_id,))
    if len(cur.fetchall()) <= 0:
        cur.execute('''
        insert into monitors (monitor_id, last_sample_id)
        values (?, ?)
        ''', (monitor_id, sample_id))
    else:
        cur.execute('''
        update monitors set last_sample_id=?  where monitor_id=?
        ''', (sample_id, monitor_id))
    conn.commit()

def mapValue(x):
    my_logger.debug('mapValue run for value: ' + x)
    return {
        'SUCCESS': 1,
        'WARNING': 2,
        'ERROR': 3,
        'INACTIVE': 0
    }[x]

def getWPMData(monitorClient, zbxHost):
    my_logger.info('start getWPMData')

    while True:
        monitors = monitorClient.listMonitors().json()
        if 'data' in monitors:
            break
        else:
            my_logger.debug('monitors object not defined, trying again after 5 seconds')
            time.sleep(5)                                           # TODO: need break after x num of tries
    my_logger.info('wpm list monitors api call complete')

    ''' time config '''
    my_logger.info('Time config start')

    t = datetime.datetime.utcnow()

    t1 = t - datetime.timedelta(minutes=0)
    t2 = t - datetime.timedelta(minutes=int(config.get('WPM', 'sample_delta_min')))
    params = {'startDate': t2.strftime("%Y-%m-%dT%H:%M"),
                'endDate': t1.strftime("%Y-%m-%dT%H:%M")}
    my_logger.info('Time config end')

    ''' get WPM data '''
    zbxPayload = {zbxHost: {}}
    for monitor in monitors['data']['items']:
        if (len(monitor['description']) > 0):
            my_logger.info('[' + monitor['description'] + '] Processing Start')
            if monitor['active']:
                my_logger.debug('[' + monitor['description'] + '] Monitor is active')
                while True:
                    time.sleep(2)
                    my_logger.debug('[' + monitor['description'] + '] Calling WPM Samples API')
                    samples = monitorClient.getMonitorSamples(monitor['id'], params).json()
                    if 'samples' in locals():
                        my_logger.debug('[' + monitor['description'] + '] samples found in locals')
                        break
                    else:
                        my_logger.debug('[' + monitor['description'] + '] wpm get samples api call fail, trying again after 5 seconds')
                        time.sleep(5)
                my_logger.debug('[' + monitor['description'] + '] wpm get samples api call complete')
                if not 'data' in samples:
                    my_logger.debug('[' + monitor['description'] + '] No data returned')
                    pass
                elif samples['data']['count'] == 0:
                    my_logger.debug('[' + monitor['description'] + '] No data available')
                    pass
                else:
                    my_logger.debug('[' + monitor['description'] + '] Status found: ' + samples['data']['items'][0]['status'])
                    my_logger.debug('[' + monitor['description'] + '] Status timestamp: ' + samples['data']['items'][0]['startTime'])
                    # pprint.pprint(samples)
                    if isNewSampleDB(monitor['id'], samples['data']['items'][0]['id']):
                        my_logger.debug('[' + monitor['description'] + '] Status is new')
                        updateSampleDB(monitor['id'], samples['data']['items'][0]['id'])
                        zbxPayload[zbxHost][monitor['description']] = mapValue(samples['data']['items'][0]['status'])
                    else:
                        my_logger.debug('[' + monitor['description'] + '] Status is old')
                        pass
            else:
                my_logger.debug('[' + monitor['description'] + '] Monitor is NOT active')
                zbxPayload[zbxHost][monitor['description']] = mapValue('INACTIVE')
            my_logger.info('[' + monitor['description'] + '] Processing complete')
    my_logger.info('end getWPMData')
    return zbxPayload

def sendZBXData(zbxPayload, zbxHost):
    my_logger.info('start sendZBXData')
    ''' zabbix_sender info '''
    zbxContainer = protobix.DataContainer("items", config.get('Zabbix Server', 'ip'), config.get('Zabbix Server', 'port'))
    zbxContainer.set_debug(False)
    zbxContainer.set_verbosity(False)

    if len(zbxPayload[zbxHost]) > 0:
        zbxContainer.add(zbxPayload)
        ''' Send data to zabbix '''
        ret = zbxContainer.send(zbxContainer)
        ''' If returns False, then we got a problem '''
        if not ret:
            my_logger.debug('Ooops. Something went wrong when sending data to Zabbix')
    else:
        my_logger.debug('no data sent, no data gathered')
    my_logger.info('end sendZBXData')


def main():
    my_logger.info('start main')

    my_logger.debug('get config info [key, secret, zbxHost]')
    key = config.get('WPM', 'api_key')
    secret = config.get('WPM', 'api_secret')
    zbxHost = config.get('Zabbix Host', 'host_name')

    my_logger.debug('get monitorClient')
    monitorClient = Monitor(key, secret)

    my_logger.debug('call function getWPMData')
    wpmData = getWPMData(monitorClient, zbxHost)
    my_logger.info('function getWPMData complete')
    my_logger.info('call function sendZBXData')
    sendZBXData(wpmData, zbxHost)
    my_logger.info('sendZBXData complete, end main')

main()
conn.close()
