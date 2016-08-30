#!/usr/bin/python

import subprocess
import argparse
import sys
import tempfile
import os
import time
import shutil

'''
Check upgrade prerequisites - run preupgrade-assistant
or only its parts if '--blocker' option is specified
'''
def check():
    if cmdline.blocker:
        check_blockers()
    else:
        subprocess.call(['preupg'])

'''
Explicitely launch VZ-specific preupgrade-assistant checkers
that check for upgrade blockers
'''
def check_blockers():
    FNULL = open(os.devnull, 'w')
    ret = subprocess.call(['yum', 'check-update'], stdout=FNULL, stderr=FNULL)
    if ret > 0:
        print "INPLACERISK: EXTREME: You have updates available! Please install all updates first"

    # We have to set these ones when calling assitant checkers outside the assistant
    os.environ["XCCDF_RESULT_FAIL"] = "1"
    os.environ["XCCDF_RESULT_PASS"] = "0"
    ret += subprocess.call(['/usr/share/preupgrade/Virtuozzo6_7/system/vzfs/check.sh'], env=os.environ)
    ret += subprocess.call(['/usr/share/preupgrade/Virtuozzo6_7/system/vzrelease/check.sh'], env=os.environ)
    ret += subprocess.call(['/usr/share/preupgrade/Virtuozzo6_7/system/prlctl/check.sh'], env=os.environ)
    ret += subprocess.call(['/usr/share/preupgrade/Virtuozzo6_7/system/ez-templates/check.sh'], env=os.environ)

    if ret == 0:
        print "No upgrade blockers found!"
    else:
        print "Critical blockers found, please fix them before trying to upgrade"

'''
Actually run upgrade by means of redhat-upgrade-tool
Preliminary launch preupgrade-assistant if it has not been launched yet
'''
def install():
    if not os.path.isdir("/root/preupgrade"):
        print "It looks like preupgrade check was not performed, launching..."
        cmdline.blocker = False
        check()

    if cmdline.boot:
        with open("/root/preupgrade/postupgrade.d/pkgdowngrades", "a") as cfg_file:
            cfg_file.write("grub2-mkconfig -O /boot/grub2/grub.cfg 2>&1 | tee -a /var/log/vzupgrade.log")
            cfg_file.write("grub2-install " + cmdline.boot + " 2>&1 | tee -a /var/log/vzupgrade.log")

    if cmdline.device:
        subprocess.call(['redhat-upgrade-tool', '--device', cmdline.device, '--cleanup-post'])
    elif cmdline.network:
        subprocess.call(['redhat-upgrade-tool', '--network', '7.0', '--instrepo', cmdline.network, '--cleanup-post'])

def list_prereq():
    print "=== Virtuozzo-specific upgrade prerequisites: ==="
    print "* No VMs exist on the host"
    print "* There are no containers that use VZFS"
    print "* There are no templates for OSes not supported by Vz7"
    print "* All updates are installed"


def parse_command_line():
    global cmdline
    parser = argparse.ArgumentParser(description="Virtuozzo Upgrade Tool")
    subparsers = parser.add_subparsers(title='command')

    sp = subparsers.add_parser('check', help='check upgrade prerequisites and generate upgrade scripts')
    sp.add_argument('--blocker', action='store_true', help='check only upgrade blockers')
    sp.set_defaults(func=check)

    sp = subparsers.add_parser('list', help='list prerequisites for in-place upgrade')
    sp.set_defaults(func=list_prereq)

    sp = subparsers.add_parser('install', help='Perform upgrade')
    sp.add_argument('--boot', action='store', help='install bootloader to a specified device')
    src_group = sp.add_mutually_exclusive_group(required=True)
    src_group.add_argument('--device', action='store', help='mounted device to be used (please provide link to folder where Vz7 iso image is mounted)')
    src_group.add_argument('--network', action='store', help='Vz7 network repository to be used')
    sp.set_defaults(func=install)

    cmdline = parser.parse_args(sys.argv[1:])


if __name__ == '__main__':
    parse_command_line()
    cmdline.func()
