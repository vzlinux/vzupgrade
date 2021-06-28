vzupgrade tool can be used to upgrade VHS from major version to another and CentOS to VzLinux with newer major version.

Normally, the vzupgrade script shouldbe installed via the RPM package from VzLinux repos:

```sh
 yum install -y yum-utils
 yum-config-manager --add-repo http://repo.virtuozzo.com/vzlinux/7/x86_64/os/
 yum install -y --nogpgcheck vzupgrade
```

Make sure to disable the VzLinux repo before real upgrade

```sh
 rm -f /etc/yum.repos.d/repo.virtuozzo*
```

Before running vzupgrade, installall CentOS updates:

```sh
 yum update -y
```

Now run the pre-upgrade check, for CentOS one should use "--skip-vz" option:

```sh
 vzupgrade check --skip-vz
```

If no problems were found, then the upgrade itself:

```sh
 vzupgrade install --skip-vz
```

The system will be rebooted into a special mode (using "Upgrade-initramfs" initrd image).
Once the upgrade is finished, the system will be automatically rebooted once again
into upgraded system.