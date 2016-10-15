#!/bin/bash

PID="`ps ax | grep rapiro_adjust.py | grep -v grep | awk '{print $1;}'`"
case "$PID" in
'') echo 'No processes found';;
*)  echo kill $PID; sudo kill -9 $PID;;
esac
