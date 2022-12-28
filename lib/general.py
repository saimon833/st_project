from command import run_command

def run_pacman(cmd: str,*args,**kwargs) -> None:
    run_command(f'pacman {cmd}')