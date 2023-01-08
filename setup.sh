#!/usr/bin/bash


pacman-key --init
pacman-key --populate archlinux

pacman -Sy
pacman -S git --noconfirm

git clone https://github.com/saimon833/st_project

cd st_project

python guided.py
