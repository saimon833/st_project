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
        # b''.join(sys_command(f'sync')) # No need to, since the underlaying fs() object will call sync.
        # TODO: https://stackoverflow.com/questions/28157929/how-to-safely-handle-an-exception-inside-a-context-manager
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
        self.pacstrap('base base-devel linux linux-firmware btrfs-progs efibootmgr nano'.split(' '))
        self.genfstab()

        with open(f'{self.mountpoint}/etc/fstab', 'a') as fstab:
            fstab.write('\ntmpfs /tmp tmpfs defaults,noatime,mode=1777 0 0\n')  # Redundant \n at the start? who knoes?

        ## TODO: Support locale and timezone
        # os.remove(f'{self.mountpoint}/etc/localtime')
        # sys_command(f'/usr/bin/arch-chroot {self.mountpoint} ln -s /usr/share/zoneinfo/{localtime} /etc/localtime')
        # sys_command('/usr/bin/arch-chroot /mnt hwclock --hctosys --localtime')
        self.set_hostname()
        self.set_locale('en_US.UTF-8')

        # TODO: Use python functions for this
        sys_command(f'/usr/bin/arch-chroot {self.mountpoint} chmod 700 /root')

        if self.partition.filesystem == 'btrfs':
            with open(f'{self.mountpoint}/etc/mkinitcpio.conf', 'w') as mkinit:
                ## TODO: Don't replace it, in case some update in the future actually adds something.
                mkinit.write('MODULES=(btrfs)\n')
                mkinit.write('BINARIES=(/usr/bin/btrfs)\n')
                mkinit.write('FILES=()\n')
                mkinit.write('HOOKS=(base udev autodetect modconf block encrypt filesystems keyboard fsck)\n')
            sys_command(f'/usr/bin/arch-chroot {self.mountpoint} mkinitcpio -p linux')

        return True

    def add_bootloader(self):
        log(f'Adding bootloader to {self.boot_partition}')
        o = b''.join(sys_command(f'/usr/bin/arch-chroot {self.mountpoint} bootctl --no-variables --path=/boot install'))
        with open(f'{self.mountpoint}/boot/loader/loader.conf', 'w') as loader:
            loader.write('default arch\n')
            loader.write('timeout 5\n')

        with open(f'{self.mountpoint}/boot/loader/entries/arch.conf', 'w') as entry:
            entry.write('title Arch Linux\n')
            entry.write('linux /vmlinuz-linux\n')
            entry.write('initrd /initramfs-linux.img\n')

            for root, folders, uids in os.walk('/dev/disk/by-partuuid'):
                for uid in uids:
                    real_path = os.path.realpath(os.path.join(root, uid))
                    if not os.path.basename(real_path) == os.path.basename(self.partition.path): continue

                    entry.write(f'options root=PARTUUID={uid} rw intel_pstate=no_hwp\n')
                    return True
                break
        raise RequirementError(
            f'Could not identify the UUID of {self.partition}, there for {self.mountpoint}/boot/loader/entries/arch.conf will be broken until fixed.')

    def add_additional_packages(self, *packages):
        self.pacstrap(*packages)

    def install_profile(self, profile):
        profile = Profile(self, profile)

        log(f'Installing network profile {profile}')
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

    def add_AUR_support(self):
        log(f'Building and installing yay support into {self.mountpoint}')
        self.add_additional_packages(['git', 'base-devel'])  # TODO: Remove if not explicitly added at one point
        o = b''.join(sys_command(f'/usr/bin/arch-chroot {self.mountpoint} sh -c "useradd -m -G wheel aibuilder"'))
        o = b''.join(sys_command(
            f"/usr/bin/sed -i 's/# %wheel ALL=(ALL) NO/%wheel ALL=(ALL) NO/' {self.mountpoint}/etc/sudoers"))

        o = b''.join(sys_command(
            f'/usr/bin/arch-chroot {self.mountpoint} sh -c "su - aibuilder -c \\"(cd /home/aibuilder; git clone https://aur.archlinux.org/yay.git)\\""'))
        o = b''.join(sys_command(
            f'/usr/bin/arch-chroot {self.mountpoint} sh -c "chown -R aibuilder.aibuilder /home/aibuilder/yay"'))
        o = b''.join(sys_command(
            f'/usr/bin/arch-chroot {self.mountpoint} sh -c "su - aibuilder -c \\"(cd /home/aibuilder/yay; makepkg -si --noconfirm)\\" >/dev/null"'))

        o = b''.join(
            sys_command(f'/usr/bin/arch-chroot {self.mountpoint} sh -c "userdel aibuilder; rm -rf /hoem/aibuilder"'))
