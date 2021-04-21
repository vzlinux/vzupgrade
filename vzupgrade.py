#!/usr/bin/python3

#
# Copyright (c) 2017-2020 Virtuozzo International GmbH. All rights reserved.
#
# Our contact details: Virtuozzo International GmbH, Vordergasse 59, 8200
# Schaffhausen, Switzerland.
#

import subprocess
import argparse
import sys
import tempfile
import os
import time
import shutil
import re
import fileinput
import glob
from shutil import copyfile

'''
Check if sshd_config has explicit PermitRootLogin. Set to 'yes' if it doesn't.

The problem is that default is different in Vz7 and Vz8
'''
def fix_sshd_config():
    # Check if we already have explicit PermitRootLogin
    with open("/etc/ssh/sshd_config") as f:
        for l in f:
            if l.strip().startswith("PermitRootLogin"):
                return

    # If we are here, we have to set explici parameter
    modified = False
    with fileinput.input(files=('/etc/ssh/sshd_config'), inplace=True) as f:
        for l in f:
            if not modified and "PermitRootLogin" in l:
                print("PermitRootLogin yes")
                modified = True
            print(l.strip())

    if modified:
        return

    # If we are here then we haven't find a place to add our line
    # Let's add it somewhere in the beginning then
    with fileinput.input(files=('/etc/ssh/sshd_config')) as f:
        for l in f:
            if not modified and not l.strip().startswith('#') and l.strip():
                print("PermitRootLogin yes")
                modified = True
            print(l)

'''
Add Vz8 repositories

TODO:
* check content of existing files if any - they should have exact repo id
* check content of existing vz7 repo files - they also should have repo id expected by us
'''
def add_repos():
    # When using --skip-vz, we use a dummy vz8 repo which actually points to the same
    # location as VzLinux8. The thing is that some packages (e.g., libvirt) are
    # assigned to "vz8" repo in pes-events and it is easier to manipulate repos
    # than pes-events.
    if cmdline.skip_vz:
        if os.path.isfile("/etc/yum.repos.d/vz8.repo"):
            os.remove("/etc/yum.repos.d/vz8.repo")
        for repo_file in ['vz8_dummy.repo', 'vzlinux8.repo']:
            if not os.path.isfile("/etc/yum.repos.d/" + repo_file):
                shutil.copyfile("/usr/share/vzupgrade/" + repo_file, "/etc/yum.repos.d/" + repo_file)
    else:
        if os.path.isfile("/etc/yum.repos.d/vz8_dummy.repo"):
            os.remove("/etc/yum.repos.d/vz8_dummy.repo")
        for repo_file in ['vz8.repo', 'vzlinux8.repo']:
            if not os.path.isfile("/etc/yum.repos.d/" + repo_file):
                shutil.copyfile("/usr/share/vzupgrade/" + repo_file, "/etc/yum.repos.d/" + repo_file)

'''
Put file with answers to required place.
Currently we don't have any questions to ask user, so just use pre-created file
'''
def add_answers():
    if not os.path.exists("/var/log/leapp"):
        os.makedirs("/var/log/leapp")
    for f in ["answerfile", "answerfile.userchoices"]:
        if os.path.isfile("/var/log/leapp/" + f):
            os.remove("/var/log/leapp/" + f)
        copyfile("/etc/leapp/answers/" + f, "/var/log/leapp/" + f)

'''
Before running check or upgrade, we should put some files to proper places
'''
def prepare_files():
    fix_sshd_config()
    add_repos()
    add_answers()

'''
Check upgrade prerequisites
'''
def check():
    prepare_files()
    if check_blockers():
        return 1
    try:
        d = dict(os.environ)
        if cmdline.skip_vz:
            d['SKIPVZ'] = '1'
        leapp_cmd = ['leapp', 'preupgrade', '--no-rhsm', '--enablerepo=vz8', '--enablerepo=vzlinux8']
        if cmdline.enablerepo:
            for repo in cmdline.enablerepo:
                leapp_cmd.append('--enablerepo=' + repo)

        if cmdline.debug:
            leapp_cmd.append('--debug')
        elif cmdline.verbose:
            leapp_cmd.append('--verbose')

        subprocess.check_call(leapp_cmd, env=d)
    except:
        return 1


'''
Check if templates are used that are not supported in Vz8
'''
def check_templates():
    invalid_templates = {}
    valid_templates=[
    "centos-7-x86_64",
    "centos-8-x86_64",
    "debian-10.0-x86_64",
    "debian-9.0-x86_64",
    "debian-8.0-x86_64",
    "debian-7.0-x86_64",
    "ubuntu-18.04-x86_64",
    "ubuntu-18.10-x86_64",
    "ubuntu-19.04-x86_64",
    "ubuntu-19.10-x86_64",
    "ubuntu-20.04-x86_64",
    "ubuntu-20.10-x86_64",
    "ubuntu-21.04-x86_64",
    "ubuntu-21.10-x86_64",
    "sles-11-x86_64",
    "sles-12-x86_64",
    "sles-15-x86_64",
    "vzlinux-7-x86_64",
    "vzlinux-8-x86_64"
    ]

    ctids = subprocess.check_output(["vzlist", "-o", "ctid", "-a", "-H"])
    if not ctids:
        return 0

    for ct in ctids.split("\n"):
        ct = ct.strip()
        if not ct:
            continue
        tmpl = subprocess.check_output(["vzpkg", "list", ct, "--os"])
        tmpl = tmpl.split()[0]
        if tmpl not in valid_templates:
            if tmpl in invalid_templates:
                invalid_templates[tmpl].append(ct)
            else:
                invalid_templates[tmpl] = [ct]

    if invalid_templates:
        print("Containers found that use templates not supported by VHS 8")
        print(invalid_templates)
        return 1

    return 0


'''
Explicitely launch VZ-specific preupgrade-assistant checkers
that check for upgrade blockers
'''
def check_blockers():
    FNULL = open(os.devnull, 'w')

    ret = subprocess.call(['yum', 'check-update'], stdout=FNULL, stderr=FNULL)
    if ret > 0:
        print("INPLACERISK: EXTREME: You have updates available! Please install all updates first")

    if not cmdline.skip_vz:
        ret += check_templates()

    if ret == 0:
        print("No upgrade blockers found!")
        return 0
    else:
        print("Critical blockers found, please fix them before trying to upgrade")
        return 1

'''
Transform build id into an integer number
'''
def get_build_hash(ver):
    ver = ver.replace(" (", ".")
    ver = ver.replace(")", "")
    try:
        [a,b,c,d] = ver.split(".")
        w = int(a)*10000 + int(b)*1000 + int(c)*100 + int(d)
        return w
    except:
        return 0


'''
Check if VA is installed

TODO: Currently this is just a stub.

We have va-agent installed on every node deployed via UI installer.
However, if agent is not active then we can safely remove it

But future of VA is unclear
'''
def update_pva():
    pva_detected = False
    proc = subprocess.Popen(["rpm", "-qa"], stdout=subprocess.PIPE)
    for line in iter(proc.stdout.readline, ''):
        if line is not None and line.startswith("va-"):
            pva_detected = True
            break

    if pva_detected:
        print("VA detected")


'''
Force all VEs to be stopped.
'''
def stop_ves():
    proc = subprocess.check_output(["prlctl", "list", "-a", "-o", "status,name"])
    if not proc:
        return

    for line in str(proc).split('\n'):
        if not line.startswith("running") and not line.startswith("suspended"):
            continue

        (status, name) = line.split()

        if status == "running":
            subprocess.call(['prlctl', 'stop', name])
        else:
            subprocess.call(['prlctl', 'start', name])
            subprocess.call(['prlctl', 'stop', name])


'''
Save different configuration parameters
'''
def save_configs():
    # Save info about vlans
    subprocess.call(['mkdir', '-p', '/var/lib/vzupgrade'])
    iflist = open('/var/lib/vzupgrade/iflist', 'w')
    subprocess.call(['ip', 'a'], stdout=iflist)
    iflist.close();

    # Info about services
    chklist = open('/var/lib/vzupgrade/services', 'w')
    subprocess.call(['chkconfig', '--list'], stdout=chklist)
    chklist.close();

    # Archive the whole /etc folder
    subprocess.call(['tar', 'czf', '/var/lib/vzupgrade/etc.tar.gz', '/etc'])

    if not cmdline.skip_vz:
        netlist = open('/var/lib/vzupgrade/net_list', 'w')
        subprocess.call(['prlsrvctl', 'net', 'list'], stdout=netlist)
        netlist.close();


'''
Actually run upgrade by means of leapp tool
leapp automatically launces preupgrade if it was not passed yet
'''
def install():
    prepare_files()
    if check_blockers():
        return 1

    # Clean up rpm __db* files - they can break update process
    for root, dirs, files in os.walk('/var/lib/rpm/__db*'):
        for f in files:
            if f.startswith("__db"):
                os.remove("/var/lib/rpm/" + f)

    d = dict(os.environ)
    if cmdline.skip_vz:
        d['SKIPVZ'] = '1'
    leapp_cmd = ['leapp', 'upgrade',  '--no-rhsm', '--enablerepo=vz8', '--enablerepo=vzlinux8']
    if cmdline.enablerepo:
        for repo in cmdline.enablerepo:
            leapp_cmd.append('--enablerepo=' + repo)

    if cmdline.debug:
        leapp_cmd.append('--debug')
    elif cmdline.verbose:
        leapp_cmd.append('--verbose')

    save_configs()
    if not cmdline.skip_vz:
        stop_ves()

    subprocess.call(leapp_cmd, env=d)

    if cmdline.reboot:
        subprocess.call(['reboot'])


def list_prereq():
    print("=== Virtuozzo-specific upgrade prerequisites: ===")
    print("* There are no templates for OSes not supported by Vz8")
    print("* All updates are installed")
#    print("* No Virtuozzo Automation packages are installed")


def parse_command_line():
    global cmdline
    parser = argparse.ArgumentParser(description="Virtuozzo Upgrade Tool. Please launch 'vzupgrade <cmd> --help' to get help for a particular command")
    subparsers = parser.add_subparsers(title='command')

    sp = subparsers.add_parser('check', help='check upgrade prerequisites and generate upgrade scripts')
    sp.add_argument('--blocker', action='store_true', help='check only upgrade blockers')
    sp.add_argument('--skip-vz', action='store_true', help='Skip VZ-specific actions')
    sp.add_argument('--enablerepo', nargs='*', action='store', help='id of additional repository to attach during upgrade. You can specify multiple repos here, e.g. "--enablerepo r1 r2 r3". Repositories should be already present in yum configuration files')
    sp.add_argument('--verbose', action='store_true', help='Print all but debug log messages (info, warning, error, critical) to stderr. By default only error and critical level messages are printed.')
    sp.add_argument('--debug', action='store_true', help='Print all available log messages (debug, info, warning, error, critical) and the output of executed commands to stderr. By default only error and critical level messages are printed.')
    sp.set_defaults(func=check)

    sp = subparsers.add_parser('list', help='list prerequisites for in-place upgrade')
    sp.set_defaults(func=list_prereq)

    sp = subparsers.add_parser('install', help='Perform upgrade')
#    sp.add_argument('--boot', action='store', help='install bootloader to a specified device')
#    sp.add_argument('--add-repo', nargs='*', action='store', help='additional repository to attach during upgrade, in the "repo_id=url" format. You can specify multiple repos here')
    sp.add_argument('--enablerepo', nargs='*', action='store', help='id of additional repository to attach during upgrade. You can specify multiple repos here, e.g. "--enablerepo r1 r2 r3". Repositories should be already present in yum configuration files')
    sp.add_argument('--reboot', action='store_true', help='Automatically reboot to start the upgrade when ready')
    sp.add_argument('--verbose', action='store_true', help='Print all but debug log messages (info, warning, error, critical) to stderr. By default only error and critical level messages are printed.')
    sp.add_argument('--debug', action='store_true', help='Print all available log messages (debug, info, warning, error, critical) and the output of executed commands to stderr. By default only error and critical level messages are printed.')
#    sp.add_argument('--clean-cache', action='store_true', help='clean downloaded packages cache')
#    sp.add_argument('--skip-post-update', action='store_true', help='do not run "yum update" after upgrade is performed and do not enabled readykernel autoupdate')
#    sp.add_argument('--disable-rk-autoupdate', action='store_true', help='disable ReadyKernel autoupdate in the upgraded system (autoupdate is enabled by default)')
    sp.add_argument('--skip-vz', action='store_true', help='Skip VZ-specific actions')
#    lic_group = sp.add_mutually_exclusive_group(required=True)
#    lic_group.add_argument('--license', action='store', help='license key for Virtuozzo 7 to be installed into upgraded system')
#    lic_group.add_argument('--skip-license-upgrade', action='store_true',
#                            help='Skip license upgrade. WARNING: You will not be able to launch any VM or container in the upgraded system until you enter a valid license!')
    sp.set_defaults(func=install)

    cmdline = parser.parse_args(sys.argv[1:])
    if not hasattr(cmdline, "func"):
        cmdline.func = install


if __name__ == '__main__':
    parse_command_line()

    try:
        cmdline.func()
    except KeyboardInterrupt:
        sys.exit(0)
