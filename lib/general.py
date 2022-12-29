import os, hashlib
from exceptions import RequirementError
from command import run_command

def run_pacman(cmd: str,*args,**kwargs) -> None:
    run_command(f'pacman {cmd}')

def gen_uid(entropy_length=256):
	return hashlib.sha512(os.urandom(entropy_length)).hexdigest()

def multisplit(s, splitters):
	s = [s,]
	for key in splitters:
		ns = []
		for obj in s:
			x = obj.split(key)
			for index, part in enumerate(x):
				if len(part):
					ns.append(part)
				if index < len(x)-1:
					ns.append(key)
		s = ns
	return s

def prerequisit_check():
	if not os.path.isdir('/sys/firmware/efi'):
		raise RequirementError('Archinstall only supports machines in UEFI mode.')

	return True