#!/usr/bin/python

#
# Copyright (c) 2017-2019 Virtuozzo International GmbH. All rights reserved.
#
# Our contact details: Virtuozzo International GmbH, Vordergasse 59, 8200
# Schaffhausen, Switzerland.
#

import prlsdkapi
from prlsdkapi import consts as pc
import subprocess
import syslog
import time

WAIT_TIMEOUT = 3
MAX_RETRIES = 20

attempts = 0
while attempts < MAX_RETRIES:
    try:
        prlsdkapi.init_server_sdk()
        _server = prlsdkapi.Server()
        _server.login_local().wait()
        break
    except:
        attempts += 1
        syslog.syslog("vzupgrade-post: waiting for dispatcher...")
        time.sleep(WAIT_TIMEOUT)

flags_running = [pc.VMS_STARTING, pc.VMS_RUNNING, pc.VMS_SUSPENDING, pc.VMS_SNAPSHOTING, pc.VMS_RESETTING, pc.VMS_PAUSING, pc.VMS_CONTINUING, pc.VMS_MOUNTED]

flags = pc.PVTF_VM | pc.PVTF_CT
ves = _server.get_vm_list_ex(nFlags=flags).wait()
for ve in ves:
    if ve.is_template():
        continue
    conf = ve.get_config()
    if not conf.get_auto_start():
        continue
    vm_info = ve.get_vm_info()
    if vm_info.get_state() in flags_running:
        continue

    # Now we have a VE which has autostart='yes' but is not running. Let's force its start
    syslog.syslog("vzupgrade-post: Starting %s" % (ve.get_uuid()))
    ve.start()
