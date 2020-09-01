#!/bin/bash
etcdctl ls srv/mysql --recursive -p | grep -v '/$' | xargs -n 1 -I% sh -c 'echo -n %:; etcdctl get %;'
