import os, json, hashlib, shlex, sys
import time, pty
from subprocess import Popen, STDOUT, PIPE, check_output
from select import epoll, EPOLLIN, EPOLLHUP
from .exceptions import *


def log(*args, **kwargs):
    string = ' '.join([str(x) for x in args])
    if supports_color():
        kwargs = {'bg': 'black', 'fg': 'white', **kwargs}
        string = stylize_output(string, **kwargs)
    print(string)


def gen_uid(entropy_length=256):
    return hashlib.sha512(os.urandom(entropy_length)).hexdigest()


def stylize_output(text: str, *opts, **kwargs):
    opt_dict = {'bold': '1', 'italic': '3', 'underscore': '4', 'blink': '5', 'reverse': '7', 'conceal': '8'}
    color_names = ('black', 'red', 'green', 'yellow', 'blue', 'magenta', 'cyan', 'white')
    foreground = {color_names[x]: '3%s' % x for x in range(8)}
    background = {color_names[x]: '4%s' % x for x in range(8)}
    RESET = '0'

    code_list = []
    if text == '' and len(opts) == 1 and opts[0] == 'reset':
        return '\x1b[%sm' % RESET
    for k, v in kwargs.items():
        if k == 'fg':
            code_list.append(foreground[v])
        elif k == 'bg':
            code_list.append(background[v])
    for o in opts:
        if o in opt_dict:
            code_list.append(opt_dict[o])
    if 'noreset' not in opts:
        text = '%s\x1b[%sm' % (text or '', RESET)
    return '%s%s' % (('\x1b[%sm' % ';'.join(code_list)), text or '')


def supports_color():
    """
	Return True if the running system's terminal supports color,
	and False otherwise.
	"""
    supported_platform = sys.platform != 'win32' or 'ANSICON' in os.environ

    is_a_tty = hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()
    return supported_platform and is_a_tty


def locate_binary(name):
    for PATH in os.environ['PATH'].split(':'):
        for root, folders, files in os.walk(PATH):
            for file in files:
                if file == name:
                    return os.path.join(root, file)
            break  


class sys_command():  
    """
	Stolen from archinstall_gui
	"""

    def __init__(self, cmd, *args, **kwargs):
        self.raw_cmd = cmd
        try:
            self.cmd = shlex.split(cmd)
        except Exception as e:
            raise ValueError(f'Incorrect string to split: {cmd}\n{e}')
        self.args = args
        self.kwargs = kwargs
        self.exit_code = None
        self.trace_log = b''

        if not self.cmd[0][0] == '/':
            self.cmd[0] = locate_binary(self.cmd[0])

        self.run()

    def __iter__(self, *args, **kwargs):
        for line in self.trace_log.split(b'\n'):
            yield line

    def __repr__(self, *args, **kwargs):
        return f"{self.cmd, self.trace_log}"

    def decode(self, fmt='UTF-8'):
        return self.trace_log.decode(fmt)

    def run(self):
        try:
            os.execv(self.cmd[0], self.cmd)
        except FileNotFoundError:
            log(f"{self.cmd[0]} does not exist.", origin='spawn', level=2)
            self.exit_code = 1
            return False

        if 'ignore_errors' in self.kwargs:
            self.exit_code = 0

        if self.exit_code != 0 and not self.kwargs['surpress_errors']:
            log(f"'{self.raw_cmd}' did not exit gracefully, exit code {self.exit_code}.")
            log(self.trace_log.decode('UTF-8'))
            raise SysCallError(
                f"'{self.raw_cmd}' did not exit gracefully, exit code {self.exit_code}.\n{self.trace_log.decode('UTF-8')}")


def prerequisit_check():
    if not os.path.isdir('/sys/firmware/efi'):
        raise RequirementError('Archinstall only supports machines in UEFI mode.')

    return True
