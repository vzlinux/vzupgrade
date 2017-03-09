#!/usr/bin/python

#
# Copyright (c) 2017 Parallels International GmbH
#

import prlsdkapi
from prlsdkapi import consts as pc
import subprocess
import syslog

prlsdkapi.init_server_sdk()
_server = prlsdkapi.Server()
_server.login_local().wait()

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
    syslog.syslog("Starting %s" % (ve.get_uuid()))
    ve.start()
