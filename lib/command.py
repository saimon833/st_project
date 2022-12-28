import subprocess
from lib.exceptions import CodeRunException


def run_command(cmd: str,*args,**kwargs) -> None:
   code: int = subprocess.call(cmd,shell=True)
   if code != 0:
     raise CodeRunException("Command run failure")