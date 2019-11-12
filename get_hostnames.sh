#!/bin/bash
#Created by
#  _____ _     _                _ _ _               
# / ____| |   (_)              | (_) |              
#| (___ | |__  ___   ____ _  __| |_| |_ _   _  __ _ 
# \___ \| '_ \| \ \ / / _` |/ _` | | __| | | |/ _` |
# ____) | | | | |\ V / (_| | (_| | | |_| |_| | (_| |
#|_____/|_| |_|_| \_/ \__,_|\__,_|_|\__|\__, |\__,_|
#                                        __/ |      
#                                       |___/       
# 
#Modified on : 08 Oct 2019


cd /root/ansible-files

ansible-playbook hostname.yml > /tmp/ansible-output.txt 2> /tmp/ansible-error.txt
exit 0
