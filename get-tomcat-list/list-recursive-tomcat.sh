#!/bin/bash
etcdctl ls tomcat --recursive -p | grep -v '/$' | xargs -n 1 -I% sh -c 'echo -n %:; etcdctl get %;'
