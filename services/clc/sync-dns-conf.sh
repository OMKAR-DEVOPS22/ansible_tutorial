#!/bin/bash

rsync -chazP resolved.conf root@10.15.21.45:/etc/systemd/
rsync -chazP resolved.conf root@10.15.21.46:/etc/systemd/
rsync -chazP resolved.conf root@10.15.21.47:/etc/systemd/
rsync -chazP resolved.conf root@10.15.21.48:/etc/systemd/
rsync -chazP resolved.conf root@10.15.21.56:/etc/systemd/
rsync -chazP resolved.conf root@10.15.21.57:/etc/systemd/
rsync -chazP resolved.conf root@10.15.21.58:/etc/systemd/
rsync -chazP resolved.conf root@10.15.21.59:/etc/systemd/
rsync -chazP resolved.conf root@10.15.21.67:/etc/systemd/
rsync -chazP resolved.conf root@10.15.21.68:/etc/systemd/
rsync -chazP resolved.conf root@10.15.21.69:/etc/systemd/
rsync -chazP resolved.conf root@10.15.21.70:/etc/systemd/
rsync -chazP resolved.conf root@10.15.21.71:/etc/systemd/
rsync -chazP resolved.conf root@10.15.21.72:/etc/systemd/
rsync -chazP resolved.conf root@10.15.21.74:/etc/systemd/
rsync -chazP resolved.conf root@10.15.21.79:/etc/systemd/
rsync -chazP resolved.conf root@10.15.21.80:/etc/systemd/
rsync -chazP resolved.conf root@10.15.21.81:/etc/systemd/
rsync -chazP resolved.conf root@10.15.21.115:/etc/systemd/


ssh root@10.15.21.45  systemctl restart systemd-resolved.service
ssh root@10.15.21.46  systemctl restart systemd-resolved.service
ssh root@10.15.21.47  systemctl restart systemd-resolved.service
ssh root@10.15.21.48  systemctl restart systemd-resolved.service
ssh root@10.15.21.56  systemctl restart systemd-resolved.service
ssh root@10.15.21.57  systemctl restart systemd-resolved.service
ssh root@10.15.21.58  systemctl restart systemd-resolved.service
ssh root@10.15.21.59  systemctl restart systemd-resolved.service
ssh root@10.15.21.67  systemctl restart systemd-resolved.service
ssh root@10.15.21.68  systemctl restart systemd-resolved.service
ssh root@10.15.21.69  systemctl restart systemd-resolved.service
ssh root@10.15.21.70  systemctl restart systemd-resolved.service
ssh root@10.15.21.71  systemctl restart systemd-resolved.service
ssh root@10.15.21.72  systemctl restart systemd-resolved.service
ssh root@10.15.21.74  systemctl restart systemd-resolved.service
ssh root@10.15.21.79  systemctl restart systemd-resolved.service
ssh root@10.15.21.80  systemctl restart systemd-resolved.service
ssh root@10.15.21.81  systemctl restart systemd-resolved.service
ssh root@10.15.21.115  systemctl restart systemd-resolved.service

