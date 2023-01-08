import os, stat

from .exceptions import *
from .disk import *
from .general import *
from .user_interaction import *
from .profiles import Profile


class Installer():
    def __init__(self, partition, boot_partition, *, profile=None, mountpoint='/mnt', hostname='ArchInstalled'):
        self.profile = profile
        self.hostname = hostname
        self.mountpoint = mountpoint

        self.partition = partition
        self.boot_partition = boot_partition

    def __enter__(self, *args, **kwargs):
        self.partition.mount(self.mountpoint)
        os.makedirs(f'{self.mountpoint}/boot', exist_ok=True)
        self.boot_partition.mount(f'{self.mountpoint}/boot')
        return self

    def __exit__(self, *args, **kwargs):
        if len(args) >= 2 and args[1]:
            raise args[1]
        log('Installation completed without any errors.', bg='black', fg='green')
        return True

    def pacstrap(self, *packages, **kwargs):
        if type(packages[0]) in (list, tuple): packages = packages[0]
        log(f'Installing packages: {packages}')

        if (sync_mirrors := sys_command('/usr/bin/pacman -Syy')).exit_code == 0:
            if (pacstrap := sys_command(f'/usr/bin/pacstrap {self.mountpoint} {" ".join(packages)}',
                                        **kwargs)).exit_code == 0:
                return True
            else:
                log(f'Could not strap in packages: {pacstrap.exit_code}')
        else:
            log(f'Could not sync mirrors: {sync_mirrors.exit_code}')

    def chroot(self,cmd):
        o = b''.join(sys_command(f'/usr/bin/arch-chroot {self.mountpoint} {cmd}'))

    def genfstab(self, flags='-Pu'):
        o = b''.join(sys_command(f'/usr/bin/genfstab -pU {self.mountpoint} >> {self.mountpoint}/etc/fstab'))
        if not os.path.isfile(f'{self.mountpoint}/etc/fstab'):
            raise RequirementError(
                f'Could not generate fstab, strapping in packages most likely failed (disk out of space?)\n{o}')
        return True

    def set_hostname(self, hostname=None):
        if not hostname: hostname = self.hostname
        with open(f'{self.mountpoint}/etc/hostname', 'w') as fh:
            fh.write(self.hostname + '\n')

    def set_locale(self, locale, encoding='UTF-8'):
        with open(f'{self.mountpoint}/etc/locale.gen', 'a') as fh:
            fh.write(f'{locale} {encoding}\n')
        with open(f'{self.mountpoint}/etc/locale.conf', 'w') as fh:
            fh.write(f'LANG={locale}\n')
        sys_command(f'/usr/bin/arch-chroot {self.mountpoint} locale-gen')

    def minimal_installation(self):
        self.pacstrap('base base-devel linux linux-firmware efibootmgr nano networkmanager grub'.split(' '))
        self.genfstab()

        with open(f'{self.mountpoint}/etc/fstab', 'a') as fstab:
            fstab.write('\ntmpfs /tmp tmpfs defaults,noatime,mode=1777 0 0\n')  # Redundant \n at the start? who knoes?

        ## TODO: Support locale and timezone
        # os.remove(f'{self.mountpoint}/etc/localtime')
        # sys_command(f'/usr/bin/arch-chroot {self.mountpoint} ln -s /usr/share/zoneinfo/{localtime} /etc/localtime')
        # sys_command('/usr/bin/arch-chroot /mnt hwclock --hctosys --localtime')
        self.set_hostname()
        self.set_locale('en_US.UTF-8')
        self.chroot('systemctl enable NetworkManager')
        # TODO: Use python functions for this
        sys_command(f'/usr/bin/arch-chroot {self.mountpoint} chmod 700 /root')

        return True

    def add_bootloader(self):
        log(f'Adding bootloader to {self.boot_partition}')
        o = b''.join(sys_command(f'/usr/bin/arch-chroot {self.mountpoint} grub-install --target=x86_64-efi '
                                 f'--efi-directory=/boot --bootloader-id=GRUB'))
        o = b''.join(sys_command(f'/usr/bin/arch-chroot {self.mountpoint} grub-mkconfig -o /boot/grub/grub.cfg'))
        log(f'Done')

    def add_additional_packages(self, *packages):
        self.pacstrap(*packages)

    def install_profile(self, profile):
        profile = Profile(self, profile)

        log(f'Installing profile {profile.name}')
        profile.install()

    def user_create(self, user: str, password=None, groups=[]):
        log(f'Creating user {user}')
        o = b''.join(sys_command(f'/usr/bin/arch-chroot {self.mountpoint} useradd -m -G wheel {user}'))
        if password:
            self.user_set_pw(user, password)
        if groups:
            for group in groups:
                o = b''.join(sys_command(f'/usr/bin/arch-chroot {self.mountpoint} gpasswd -a {user} {group}'))

    def user_set_pw(self, user, password):
        log(f'Setting password for {user}')
        o = b''.join(
            sys_command(f"/usr/bin/arch-chroot {self.mountpoint} sh -c \"echo '{user}:{password}' | chpasswd\""))
        pass
