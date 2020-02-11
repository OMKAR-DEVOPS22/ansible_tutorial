#!/bin/bash
etcdctl ls ubuntu-version --recursive -p | grep -v '/$' | xargs -n 1 -I% sh -c 'echo -n %:; etcdctl get %;'
