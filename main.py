
import archinstall, getpass

archinstall.sys_command(f'umount -R /mnt', surpress_errors=True)

# Select a harddrive and a disk password
harddrive = archinstall.select_disk(archinstall.all_disks())
disk_password = getpass.getpass(prompt='Disk password (won\'t echo): ')

with archinstall.Filesystem(harddrive, archinstall.GPT) as fs:
	# Use the entire disk instead of setting up partitions on your own
	fs.use_entire_disk('luks2')

	if harddrive.partition[1].size == '512M':
		raise OSError('Trying to encrypt the boot partition for petes sake..')
	harddrive.partition[0].format('fat32')

	with archinstall.luks2(harddrive.partition[1], 'luksloop', disk_password) as unlocked_device:
		unlocked_device.format('btrfs')
		
		with archinstall.Installer(unlocked_device, hostname='testmachine') as installation:
			if installation.minimal_installation():
				installation.add_bootloader(harddrive.partition[0])

				installation.add_additional_packages(['nano', 'wget', 'git'])
				installation.install_profile('workstation')

				installation.user_create('anton', 'test')
				installation.user_set_pw('root', 'toor')

				installation.add_AUR_support()