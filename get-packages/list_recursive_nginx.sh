#!/bin/bash
etcdctl ls nginx-ver --recursive -p | grep -v '/$' | xargs -n 1 -I% sh -c 'echo -n %:; etcdctl get %;'
