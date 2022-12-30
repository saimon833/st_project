import glob, re, os, json
from collections import OrderedDict
from .exceptions import *
from .general import sys_command

ROOT_DIR_PATTERN = re.compile('^.*?/devices')
GPT = 0b00000001

class BlockDevice():
	def __init__(self, path, info):
		self.path = path
		self.info = info
		self.part_cache = OrderedDict()

	@property
	def device(self):
		if not 'type' in self.info: raise DiskError(f'Could not locate backplane info for "{self.path}"')

		if self.info['type'] == 'loop':
			for drive in json.loads(b''.join(sys_command(f'losetup --json', hide_from_log=True)).decode('UTF_8'))['loopdevices']:
				if not drive['name'] == self.path: continue

				return drive['back-file']
		elif self.info['type'] == 'disk':
			return self.path

	@property
	def partitions(self):
		o = b''.join(sys_command(f'partprobe {self.path}'))

		o = b''.join(sys_command(f'/usr/bin/lsblk -J {self.path}'))
		if b'not a block device' in o:
			raise DiskError(f'Can not read partitions off something that isn\'t a block device: {self.path}')

		if not o[:1] == b'{':
			raise DiskError(f'Error getting JSON output from:', f'/usr/bin/lsblk -J {self.path}')

		r = json.loads(o.decode('UTF-8'))
		if len(r['blockdevices']) and 'children' in r['blockdevices'][0]:
			root_path = f"/dev/{r['blockdevices'][0]['name']}"
			for part in r['blockdevices'][0]['children']:
				part_id = part['name'][len(os.path.basename(self.path)):]
				if part_id not in self.part_cache:
					self.part_cache[part_id] = Partition(root_path + part_id, part_id=part_id, size=part['size'])

		return {k: self.part_cache[k] for k in sorted(self.part_cache)}

	@property
	def partition(self):
		all_partitions = self.partitions
		return [all_partitions[k] for k in all_partitions]

	def __repr__(self, *args, **kwargs):
		return f"BlockDevice({self.device})"

	def __getitem__(self, key, *args, **kwargs):
		if not key in self.info:
			raise KeyError(f'{self} does not contain information: "{key}"')
		return self.info[key]

class Partition():
	def __init__(self, path, part_id=None, size=-1, filesystem=None, mountpoint=None):
		if not part_id: part_id = os.path.basename(path)
		self.path = path
		self.part_id = part_id
		self.mountpoint = mountpoint
		self.filesystem = filesystem 
		self.size = size 

	def __repr__(self, *args, **kwargs):
		return f'Partition({self.path}, fs={self.filesystem}, mounted={self.mountpoint})'

	def format(self, filesystem):
		print(f'Formatting {self} -> {filesystem}')
		if filesystem == 'fat32':
			o = b''.join(sys_command(f'/usr/bin/mkfs.vfat -F32 {self.path}'))
			if (b'mkfs.fat' not in o and b'mkfs.vfat' not in o) or b'command not found' in o:
				raise DiskError(f'Could not format {self.path} with {filesystem} because: {o}')
			self.filesystem = 'fat32'
		else:
			raise DiskError(f'Fileformat {filesystem} is not yet implemented.')
		return True

	def mount(self, target, fs=None, options=''):
		if not self.mountpoint:
			print(f'Mounting {self} to {target}')
			if not fs:
				if not self.filesystem: raise DiskError(f'Need to format (or define) the filesystem on {self} before mounting.')
				fs = self.filesystem
			if sys_command(f'/usr/bin/mount {self.path} {target}').exit_code == 0:
				self.mountpoint = target
				return True
		
class Filesystem():
	def __init__(self, blockdevice, mode=GPT):
		self.blockdevice = blockdevice
		self.mode = mode

	def __enter__(self, *args, **kwargs):
		if self.mode == GPT:
			if sys_command(f'/usr/bin/parted -s {self.blockdevice.device} mklabel gpt',).exit_code == 0:
				return self
			else:
				raise DiskError(f'Problem setting the partition format to GPT:', f'/usr/bin/parted -s {self.blockdevice.device} mklabel gpt')
		else:
			raise DiskError(f'Unknown mode selected to format in: {self.mode}')

	def __exit__(self, *args, **kwargs):
		if len(args) >= 2 and args[1]:
			raise args[1]
		b''.join(sys_command(f'sync'))
		return True

	def raw_parted(self, string:str):
		x = sys_command(f'/usr/bin/parted -s {string}')
		o = b''.join(x)
		return x

	def parted(self, string:str):
		return self.raw_parted(string).exit_code

	def use_entire_disk(self, prep_mode=None):
		self.add_partition('primary', start='1MiB', end='513MiB', format='fat32')
		self.set_name(0, 'EFI')
		self.set(0, 'boot on')
		self.set(0, 'esp on') 
		self.add_partition('primary', start='513MiB', end='513MiB', format='ext4')

	def add_partition(self, type, start, end, format=None):
		print(f'Adding partition to {self.blockdevice}')
		if format:
			return self.parted(f'{self.blockdevice.device} mkpart {type} {format} {start} {end}') == 0
		else:
			return self.parted(f'{self.blockdevice.device} mkpart {type} {start} {end}') == 0

	def set_name(self, partition:int, name:str):
		return self.parted(f'{self.blockdevice.device} name {partition+1} "{name}"') == 0

	def set(self, partition:int, string:str):
		return self.parted(f'{self.blockdevice.device} set {partition+1} {string}') == 0

def device_state(name, *args, **kwargs):
	if os.path.isfile('/sys/block/{}/device/block/{}/removable'.format(name, name)):
		with open('/sys/block/{}/device/block/{}/removable'.format(name, name)) as f:
			if f.read(1) == '1':
				return

	path = ROOT_DIR_PATTERN.sub('', os.readlink('/sys/block/{}'.format(name)))
	hotplug_buses = ("usb", "ieee1394", "mmc", "pcmcia", "firewire")
	for bus in hotplug_buses:
		if os.path.exists('/sys/bus/{}'.format(bus)):
			for device_bus in os.listdir('/sys/bus/{}/devices'.format(bus)):
				device_link = ROOT_DIR_PATTERN.sub('', os.readlink('/sys/bus/{}/devices/{}'.format(bus, device_bus)))
				if re.search(device_link, path):
					return
	return True

def all_disks(*args, **kwargs):
	if not 'partitions' in kwargs: kwargs['partitions'] = False
	drives = OrderedDict()
	for drive in json.loads(b''.join(sys_command(f'lsblk --json -l -n -o path,size,type,mountpoint,label,pkname', *args, **kwargs, hide_from_log=True)).decode('UTF_8'))['blockdevices']:
		if not kwargs['partitions'] and drive['type'] == 'part': continue

		drives[drive['path']] = BlockDevice(drive['path'], drive)
	return drives