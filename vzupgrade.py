#!/usr/bin/python

#
# Copyright (c) 2017-2019 Virtuozzo International GmbH. All rights reserved.
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
import yum
from lxml import etree

DEFAULT_NETWORK_REPO="http://repo.virtuozzo.com/vz/releases/7.0/x86_64/os/"

'''
Check upgrade prerequisites - run preupgrade-assistant
or only its parts if '--blocker' option is specified
'''
def check():
    if not cmdline.skip_vz and check_blockers() > 0:
        sys.exit(1)
    if cmdline.skip_vz and not os.path.isfile("/etc/virtuozzo-release"):
        f = open("/etc/virtuozzo-release")
        f.write("Virtuozzo release 6.0.12", "w")
        f.close()

    if not cmdline.blocker:
        subprocess.call(['preupg'])

'''
Check if we have VM backups and notify about new backup location if yes
'''
def check_vm_backups():
    if os.path.exists("/var/parallels/backups") and os.path.isdir("/var/parallels/backups"):
        if os.listdir("/var/parallels/backups"):
            print("WARNING: We have detected that /var/parallels/backups folder is not empty.")
            print("         In Virtuozzo 7 default location for VM backups has been changed to /vz/vmprivate/backups.")
            print("         If you want to use your backups after upgrade, you will have to move them to the new location manually.")

'''
Explicitely launch VZ-specific preupgrade-assistant checkers
that check for upgrade blockers
'''
def check_blockers():
    FNULL = open(os.devnull, 'w')

    ret = subprocess.call(['yum', 'check-update'], stdout=FNULL, stderr=FNULL)
    if ret > 0:
        print("INPLACERISK: EXTREME: You have updates available! Please install all updates first")

    # We have to set these ones when calling assitant checkers outside the assistant
    os.environ["XCCDF_RESULT_FAIL"] = "1"
    os.environ["XCCDF_RESULT_PASS"] = "0"
    # pstorage upgrade script uses this as an exit code in case of failure
    os.environ["XCCDF_RESULT_INFORMATIONAL"] = "2"
    os.environ["XCCDF_VALUE_TMP_PREUPGRADE"] = "/root/preupgrade"
    os.environ["XCCDF_VALUE_SOLUTION_FILE"] = "solution.txt"
    ret += subprocess.call(['/usr/share/preupgrade/Virtuozzo6_7/system/vzfs/check.sh'], env=os.environ)
    ret += subprocess.call(['/usr/share/preupgrade/Virtuozzo6_7/system/vzrelease/check.sh'], env=os.environ)
    ret += subprocess.call(['/usr/share/preupgrade/Virtuozzo6_7/system/prlctl/check.sh'], env=os.environ)
    ret += subprocess.call(['/usr/share/preupgrade/Virtuozzo6_7/system/ez-templates/check.sh'], env=os.environ)
    ret += subprocess.call(['/usr/share/preupgrade/Virtuozzo6_7/storage/pstorage/check.py'], env=os.environ)

    check_vm_backups()

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
repomd.xml on iso doesn't contain build id
Let's add it on the basis of .discinfo file
'''
def fix_repomd():
    product_distro = "cpe:/o:virtuozzoproject:vz:7"
    yb = yum.YumBase()
    yb.disablePlugins()

    try:
        f = open("/var/lib/upgrade_pkgs/.discinfo", "r")
        for  l in f.readlines():
            if not l.startswith("Virtuozzo"):
                continue
            buildid = l.replace("Virtuozzo ", "").rstrip()
            break
        f.close()

        if cmdline.add_repo:
            # If we have additional repos, extract repo ids from them
            # and choose the highest one
            idx = 0
            w = get_build_hash(buildid)
            for rep in cmdline.add_repo:
                yb.add_enable_repo("vzupgrade_repo" + str(idx), [rep.split('=')[1]])
                for repo in yb.repos.findRepos("vzupgrade_repo" + str(idx)):
                    if repo._getRepoXML().tags['distro'] and product_distro in repo._getRepoXML().tags['distro']:
                        ver = repo._getRepoXML().tags['distro'][product_distro].pop()
                        new_w = get_build_hash(ver)
                        if new_w > w:
                            buildid = ver
                            w = new_w
                idx+=1

        tree = etree.parse("/var/lib/upgrade_pkgs/repodata/repomd.xml")
        repoid = etree.Element("tags")
        content = etree.Element("content")
        content.text = "binary-x86_64"
        distro = etree.Element("distro", cpeid="cpe:/o:virtuozzoproject:vz:7")
        distro.text = buildid
        repoid.insert(0, content)
        repoid.insert(1, distro)
        tree.getroot().insert(1, repoid)

        f = open("/var/lib/upgrade_pkgs/repodata/repomd.xml", "w")
        f.write(etree.tostring(tree.getroot()))
        f.close()
    except:
        print("Failed to set build id for the upgraded system, /etc/virtuozzo-release may contain a dummy build number.")
        pass


'''
Check if PVA is installed and add routines for its upgrade if yes
'''
def update_pva():
    pva_detected = False
    proc = subprocess.Popen(["rpm", "-qa"], stdout=subprocess.PIPE)
    for line in iter(proc.stdout.readline, ''):
        if line is not None and line.startswith("pva-"):
            pva_detected = True

    if pva_detected:
        subprocess.call(['rm', '-rf', '/var/lib/pva_upgrade'])
        subprocess.call(['mkdir', '-p', '/var/lib/pva_upgrade'])
        if os.path.isfile("/var/opt/pva/agent/etc/eid"):
            subprocess.call(['cp', "/var/opt/pva/agent/etc/eid", '/var/lib/pva_upgrade/'])
        if os.path.isfile("/var/opt/pva/agent/etc/vzagent.conf"):
            subprocess.call(['cp', "/var/opt/pva/agent/etc/vzagent.conf", '/var/lib/pva_upgrade/'])
        if os.path.isfile("/etc/opt/pva/pp/plugins/httpd/include.ssl.conf"):
            subprocess.call(['cp', "/etc/opt/pva/pp/plugins/httpd/include.ssl.conf", '/var/lib/pva_upgrade/'])

        if os.path.isfile('/etc/init.d/pvapp'):
            subprocess.call(['/etc/init.d/pvapp', 'stop'])
        if os.path.isfile('/etc/init.d/pvaagentd'):
            subprocess.call(['/etc/init.d/pvaagentd', 'stop'])
        with open("/root/preupgrade/postupgrade.d/pkgdowngrades/fixpkgdowngrades.sh", "a") as cfg_file:
            cfg_file.write("rpm -qa pva* | xargs yum remove -y 2>&1 | tee -a /var/log/vzupgrade.log\n")
            cfg_file.write("rm -rf /var/opt/pva/setup 2>&1 | tee -a /var/log/vzupgrade.log\n")
            cfg_file.write("wget http://repo.virtuozzo.com/va-agent/deploy-va-agent/deploy-va-agent -O /tmp/deploy-va-agent 2>&1 | tee -a /var/log/vzupgrade.log\n")
            cfg_file.write("sh /tmp/deploy-va-agent 2>&1 | tee -a /var/log/vzupgrade.log\n")
            cfg_file.write("echo 'prlctl delete 1 2>&1 | tee -a /var/log/vzupgrade.log' >> /var/lib/vzupgrade/vzupgrade-post\n")

    with open("/root/preupgrade/postupgrade.d/pkgdowngrades/fixpkgdowngrades.sh", "a") as cfg_file:
        cfg_file.write("echo 'systemctl disable vzupgrade 2>&1 | tee -a /var/log/vzupgrade.log' >> /var/lib/vzupgrade/vzupgrade-post\n")
        cfg_file.write("echo 'rm -f /etc/systemd/system/vzupgrade.service 2>&1 | tee -a /var/log/vzupgrade.log' >> /var/lib/vzupgrade/vzupgrade-post\n")


'''
Force all VEs to be stopped. We can't suspend them due to different
resume procedure in Vz7
'''
def stop_ves():
    proc = subprocess.Popen(["prlctl", "list", "-a", "-o", "status,name"], stdout=subprocess.PIPE)
    for line in iter(proc.stdout.readline, ''):
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
    netlist = open('/var/lib/vzupgrade/net_list', 'w')
    subprocess.call(['prlsrvctl', 'net', 'list'], stdout=netlist)
    netlist.close();
    iflist = open('/var/lib/vzupgrade/iflist', 'w')
    subprocess.call(['ifconfig'], stdout=iflist)
    iflist.close();

    # Save dispatcher config
    subprocess.call(['cp', '/etc/parallels/dispatcher.xml', '/var/lib/vzupgrade'])

    # Info about services
    chklist = open('/var/lib/vzupgrade/services', 'w')
    subprocess.call(['chkconfig', '--list'], stdout=chklist)
    chklist.close();

    # Archive the whole /etc folder
    subprocess.call(['tar', 'czf', '/var/lib/vzupgrade/etc.tar.gz', '/etc'])

'''
Check that packages that are going to be used for upgrade
contains at least the very minimal basis - absence of some packages
guarantees that upgrade will fail
'''
def check_upgrade_sanity():
    pkg_line = ''
    packages = ['glibc*x86_64*', 'systemd*x86_64*']
    if os.path.isfile("/var/lib/system-upgrade/package.list"):
        f = open("/var/lib/system-upgrade/package.list")
        pkg_line = '|'.join(f.readlines())
        f.close()

    for pkg in packages:
        if not glob.glob("/var/lib/system-upgrade/" + pkg) \
                and not re.search(pkg.replace("*", ".*"), pkg_line):
            print("!!!!!!!!!!!! FINAL CHECK FAILED, DO NOT RUN THE UPGRADE !!!!!!!!!!!!")
            print("Can't find %s among upgrade packages. Did you forget to specify additionaly repositories?" % pkg)
            print("The upgrade will likely fail, but you can reboot and proceed at your own risk.")
            sys.exit(1)

'''
Download packages from additional repositories
'''
def download_pkgs():
    if not cmdline.add_repo:
        return

    idx=0
    for rep in cmdline.add_repo:
        net_target = re.sub(r'.*://', '', rep)
        net_target = re.sub(r'/$', '', net_target)
        target_folders = net_target.split("/")
        rep = re.sub(r'.*=', '', rep)
        rep_name = '/var/lib/upgrade_pkgs' + str(idx)
        if cmdline.clean_cache:
            subprocess.call(['rm', '-rf', rep_name])
        subprocess.call(['wget', '-r', '-c', '-nH', '--cut-dirs', str(len(target_folders)-1), '--no-parent', rep + "/Packages/", '-P', rep_name])
        subprocess.call(['wget', '-r', '-c', '-nH', '--cut-dirs', str(len(target_folders)-1), '--no-parent', rep + "/repodata/", '-P', rep_name])
        try:
            subprocess.call(['wget', '-r', '-c', '-nH', '--cut-dirs', str(len(target_folders)-1), '--no-parent', rep + "/.discinfo", '-P', rep_name])
        except:
            pass
        idx += 1


'''
Actually run upgrade by means of redhat-upgrade-tool
Preliminary launch preupgrade-assistant if it has not been launched yet
'''
def install():
    if not os.path.isdir("/root/preupgrade"):
        print("It looks like preupgrade check was not performed, launching...")
        cmdline.blocker = False
        check()

    if cmdline.boot:
        with open("/root/preupgrade/postupgrade.d/pkgdowngrades/fixpkgdowngrades.sh", "a") as cfg_file:
            cfg_file.write("grub2-mkconfig -o /boot/grub2/grub.cfg 2>&1 | tee -a /var/log/vzupgrade.log\n")
            cfg_file.write("grub2-install " + cmdline.boot + " 2>&1 | tee -a /var/log/vzupgrade.log")

    if not os.path.exists("/root/preupgrade/postupgrade.d/pkgdowngrades/fixpkgdowngrades.sh"):
       os.makedirs("/root/preupgrade/postupgrade.d/pkgdowngrades")
       open("/root/preupgrade/postupgrade.d/pkgdowngrades/fixpkgdowngrades.sh", "w").close()

    if cmdline.disable_rk_autoupdate or cmdline.skip_post_update:
        with open("/root/preupgrade/postupgrade.d/pkgdowngrades/fixpkgdowngrades.sh", "a") as cfg_file:
            cfg_file.write("/sbin/readykernel autoupdate disable 2>&1 | tee -a /var/log/vzupgrade.log\n")
    else:
        with open("/root/preupgrade/postupgrade.d/pkgdowngrades/fixpkgdowngrades.sh", "a") as cfg_file:
            cfg_file.write("/sbin/readykernel autoupdate enable 2>&1 | tee -a /var/log/vzupgrade.log\n")

    if cmdline.skip_post_update:
        cfg_file = fileinput.FileInput("/root/preupgrade/postupgrade.d/pkgdowngrades/fixpkgdowngrades.sh", inplace=True)
        for line in cfg_file:
            if line.startswith("yum update --disablerepo=factory"):
                print(line.replace("yum update", "#yum update").rstrip())
            elif line.startswith("yum groupupdate --disablerepo=factory"):
                print(line.replace("yum groupupdate", "#yum groupupdate").rstrip())
            elif line.startswith("yum distro-sync --disablerepo=factory"):
                print(line.replace("yum distro-sync --disablerepo=factory", "#yum distro-sync --disablerepo=factory").rstrip())
            else:
                print(line.rstrip())

    if cmdline.skip_license_upgrade:
        print('WARNING: Skipping license upgrade. You will not be able to launch any VM or container in the upgraded system until you enter a valid license!')
        cfg_file = fileinput.FileInput("/root/preupgrade/postupgrade.d/pkgdowngrades/fixpkgdowngrades.sh", inplace=True)
        for line in cfg_file:
            if line.startswith("vzlicupdate -n"):
                print(line.replace("vzlicupdate -n", "#vzlicupdate -n").rstrip())
            else:
                print(line.rstrip())
        cfg_file = fileinput.FileInput("/var/lib/vzupgrade/vzupgrade-post", inplace=True)
        for line in cfg_file:
            if line.startswith("/var/lib/vzupgrade/vzupgrade-post-ves"):
                print(line.replace("/var/lib/vzupgrade/vzupgrade-post-ves", "#/var/lib/vzupgrade/vzupgrade-post-ves").rstrip())
            else:
                print(line.rstrip())
    elif cmdline.license:
        cfg_file = fileinput.FileInput("/root/preupgrade/postupgrade.d/pkgdowngrades/fixpkgdowngrades.sh", inplace=True)
        for line in cfg_file:
            if line.startswith("vzlicupdate -n"):
                print(line.replace("vzlicupdate -n", "vzlicload -p " + cmdline.license).rstrip())
            else:
                print(line.rstrip())
        cfg_file = fileinput.FileInput("/var/lib/vzupgrade/vzupgrade-post", inplace=True)
        for line in cfg_file:
            if line.startswith("#/var/lib/vzupgrade/vzupgrade-post-ves"):
                print(line.replace("#/var/lib/vzupgrade/vzupgrade-post-ves", "/var/lib/vzupgrade/vzupgrade-post-ves").rstrip())
            else:
                print(line.rstrip())

    # No need in ELS check during upgrade
    if os.path.isfile("/etc/yum/pluginconf.d/pre-transaction-actions.conf"):
        els_cfg = fileinput.FileInput("/etc/yum/pluginconf.d/pre-transaction-actions.conf", inplace=True)
        for line in els_cfg:
            if line.startswith("enabled"):
                print("enabled = 0")
            else:
                print(line.rstrip())

    if not cmdline.skip_vz:
        update_pva()

    # Clean up rpm __db* files - they can break update process
    for root, dirs, files in os.walk('/var/lib/rpm/__db*'):
        for f in files:
            if f.startswith("__db"):
                os.remove("/var/lib/rpm/" + f)

    subprocess.call(['preupgrade-pstorage'])
    # It's ot enough for us to have grep in "downgraded" list, we want to update it before
    # that list is processed. So downgrade it to the released version first.
    # Actually this doesn't seem to be required after VzLinux updated to 7.3,
    # but let's leave for safety, just hide the output
    FNULL = open(os.devnull, 'w')
    subprocess.call(['yum', 'downgrade', '-y', '--disablerepo', 'virtuozzolinux-updates', 'grep'], stdout=FNULL, stderr=FNULL)

    # Disable our repos since sometimes yum manages to pick up packages from there
    # during upgrade
    # Note that redhat-upgrade-tool scans disabled repos during upgrade. So just move
    # repo files out of /etc/yum.repos.d
    subprocess.call(['mv', '/etc/yum.repos.d', '/etc/yum.repos.d.orig'])
    subprocess.call(['mkdir', '/etc/yum.repos.d'])

    # Remove vzcreaterepo since it is not updated by anything in Vz7
    # but depends on createrepo which in turn depends on python-2.6
    # Due to this yum can try to look for python-2.6 during upgrade
    subprocess.call(['yum', 'remove', '-y', 'vzcreaterepo', 'createrepo'])

    subprocess.call(['rm', '-rf', '/var/lib/upgrade_pkgs'])
    subprocess.call(['rm', '-rf', '/var/tmp/system-upgrade'])
    subprocess.call(['mkdir', '-p', '/var/lib/upgrade_pkgs'])

    if not cmdline.skip_vz:
        save_configs()
        stop_ves()

    if cmdline.device:
        if cmdline.device.startswith("/dev"):
            tmpfolder = tempfile.mkdtemp()
            ret = subprocess.call(['mount', cmdline.device, tmpfolder])
            if ret > 0:
                print("Tried to mount " + cmdline.device + " but failed")
                sys.exit(1)
            cmdline.device = tmpfolder
        elif cmdline.device.endswith(".iso") and os.path.isfile(cmdline.device):
            tmpfolder = tempfile.mkdtemp()
            ret = subprocess.call(['mount', '-o', 'loop', cmdline.device, tmpfolder])
            if ret > 0:
                print("Tried to mount " + cmdline.device + " but failed")
                sys.exit(1)
            cmdline.device = tmpfolder

        subprocess.call(['cp', '-r', cmdline.device + "/Packages/", '/var/lib/upgrade_pkgs'])
        subprocess.call(['cp', '-r', cmdline.device + "/repodata/", '/var/lib/upgrade_pkgs'])
        subprocess.call(['cp', cmdline.device + "/.discinfo", '/var/lib/upgrade_pkgs'])

        if not cmdline.skip_vz:
            fix_repomd()
        download_pkgs()
        cmd = ['redhat-upgrade-tool', '--device', cmdline.device, '--cleanup-post']
        if cmdline.add_repo:
            for rep in cmdline.add_repo:
                cmd.append('--addrepo')
                cmd.append(rep)

        subprocess.call(cmd)
        check_upgrade_sanity()
        if cmdline.reboot:
            subprocess.call(['reboot'])
    elif cmdline.network:
        if cmdline.network.endswith(".iso"):
            subprocess.call(['wget', cmdline.network, '-O', '/var/tmp/vzupgrade.iso'])
            cmd = ['redhat-upgrade-tool', '--iso', '/var/tmp/vzupgrade.iso', '--cleanup-post']
            if not cmdline.skip_vz:
               fix_repomd()
            download_pkgs()
        else:
            # Cound number of folders to be cut in address
            # (when passing argument to --cut-dirs wget option)
            net_target = re.sub(r'.*://', '', cmdline.network)
            net_target = re.sub(r'/$', '', net_target)
            target_folders = net_target.split("/")
            subprocess.call(['wget', '-r', '-nH', '--cut-dirs', str(len(target_folders)-1), '--no-parent', cmdline.network + "/Packages/", '-P', '/var/lib/upgrade_pkgs'])
            subprocess.call(['wget', '-r', '-nH', '--cut-dirs', str(len(target_folders)-1), '--no-parent', cmdline.network + "/repodata/", '-P', '/var/lib/upgrade_pkgs'])
            subprocess.call(['wget', '-r', '-nH', '--cut-dirs', str(len(target_folders)-1), '--no-parent', cmdline.network + "/.discinfo", '-P', '/var/lib/upgrade_pkgs'])

            if not cmdline.skip_vz:
               fix_repomd()
            download_pkgs()
            cmd = ['redhat-upgrade-tool', '--network', '7.0', '--instrepo', cmdline.network, '--cleanup-post']

        if cmdline.add_repo:
            for rep in cmdline.add_repo:
                cmd.append('--addrepo')
                cmd.append(rep)

        subprocess.call(cmd)
        check_upgrade_sanity()
        if cmdline.reboot:
            subprocess.call(['reboot'])

def list_prereq():
    print("=== Virtuozzo-specific upgrade prerequisites: ===")
    print("* No VMs exist on the host")
    print("* There are no containers that use VZFS")
    print("* There are no templates for OSes not supported by Vz7")
    print("* All updates are installed")
    print("* No Virtuozzo Automation packages are installed")


def parse_command_line():
    global cmdline
    parser = argparse.ArgumentParser(description="Virtuozzo Upgrade Tool. Please launch 'vzupgrade <cmd> --help' to get help for a particular command")
    subparsers = parser.add_subparsers(title='command')

    sp = subparsers.add_parser('check', help='check upgrade prerequisites and generate upgrade scripts')
    sp.add_argument('--blocker', action='store_true', help='check only upgrade blockers')
    sp.add_argument('--skip-vz', action='store_true', help='Skip VZ-specific actions')
    sp.set_defaults(func=check)

    sp = subparsers.add_parser('list', help='list prerequisites for in-place upgrade')
    sp.set_defaults(func=list_prereq)

    sp = subparsers.add_parser('install', help='Perform upgrade')
    sp.add_argument('--boot', action='store', help='install bootloader to a specified device')
    sp.add_argument('--add-repo', nargs='*', action='store', help='additional repository to attach during upgrade, in the "repo_id=url" format. You can specify multiple repos here')
    sp.add_argument('--reboot', action='store_true', help='automatically reboot to start the upgrade when ready')
    sp.add_argument('--clean-cache', action='store_true', help='clean downloaded packages cache')
    sp.add_argument('--skip-post-update', action='store_true', help='do not run "yum update" after upgrade is performed and do not enabled readykernel autoupdate')
    sp.add_argument('--disable-rk-autoupdate', action='store_true', help='disable ReadyKernel autoupdate in the upgraded system (autoupdate is enabled by default)')
    sp.add_argument('--skip-vz', action='store_true', help='Skip VZ-specific actions')
    src_group = sp.add_mutually_exclusive_group()
    src_group.add_argument('--device', action='store', help='mounted device to be used (please provide link to folder where Vz7 iso image is mounted)')
    src_group.add_argument('--network', action='store', help='Vz7 network repository to be used')
    lic_group = sp.add_mutually_exclusive_group(required=True)
    lic_group.add_argument('--license', action='store', help='license key for Virtuozzo 7 to be installed into upgraded system')
    lic_group.add_argument('--skip-license-upgrade', action='store_true',
                            help='Skip license upgrade. WARNING: You will not be able to launch any VM or container in the upgraded system until you enter a valid license!')
    sp.set_defaults(func=install)

    cmdline = parser.parse_args(sys.argv[1:])


if __name__ == '__main__':
    parse_command_line()

    if cmdline.func == 'install':
        if not cmdline.device and not cmdline.network:
            cmdline.network = DEFAULT_NETWORK_REPO
        if (cmdline.device or cmdline.network == DEFAULT_NETWORK_REPO) and not cmdline.add_repo:
            cmdline.add_repo = "vzlinux7=http://repo.virtuozzo.com/vzlinux/7/x86_64/os/"

    try:
        cmdline.func()
    except KeyboardInterrupt:
        sys.exit(0)
