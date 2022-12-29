import subprocess
from lib.exceptions import CodeRunException


def run_command(cmd: str,*args,**kwargs) -> str:
    output: subprocess = subprocess.run(cmd.split(),stdout=subprocess.PIPE)
    if output.returncode != 0:
      raise CodeRunException("Code run failed.")
    return output.stdout