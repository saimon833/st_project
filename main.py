import archinstall, getpass

# Unmount and close previous runs
archinstall.sys_command(f'umount -R /mnt', surpress_errors=True)

# Select a harddrive and a disk password
harddrive = archinstall.select_disk(archinstall.all_disks())

def perform_installation(device, boot_partition):
	hostname = input('Desired hostname for the installation: ')
	with archinstall.Installer(device, hostname=hostname) as installation:
		if installation.minimal_installation():
			installation.add_bootloader(boot_partition)

			packages = input('Additional packages aside from base (space separated): ').split(' ')
			if len(packages) and packages[0] != '':
				installation.add_additional_packages(packages)

			profile = input('Any particular profile you want to install: ')
			if len(profile.strip()):
				installation.install_profile(profile)

			while 1:
				new_user = input('Any additional users to install (leave blank for no users): ')
				if not len(new_user.strip()): break
				new_user_passwd = getpass.getpass(prompt=f'Password for user {new_user}: ')
				new_user_passwd_verify = getpass.getpass(prompt=f'Enter password again for verification: ')
				if new_user_passwd != new_user_passwd_verify:
					archinstall.log(' * Passwords did not match * ', bg='black', fg='red')
					continue

				installation.user_create(new_user, new_user_passwd)

			while (root_pw := getpass.getpass(prompt='Enter root password (leave blank for no password): ')):
				root_pw_verification = getpass.getpass(prompt='And one more time for verification: ')
				if root_pw != root_pw_verification:
					archinstall.log(' * Passwords did not match * ', bg='black', fg='red')
					continue
				installation.user_set_pw('root', root_pw)
				break


with archinstall.Filesystem(harddrive, archinstall.GPT) as fs:
	fs.use_entire_disk('ext4')

	if harddrive.partition[1].size == '512M':
		raise OSError('Trying to encrypt the boot partition for petes sake..')
	harddrive.partition[0].format('fat32')

	harddrive.partition[1].format('ext4')
	perform_installation(harddrive.partition[1], harddrive.partition[0])