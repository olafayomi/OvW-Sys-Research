#!/usr/bin/expect

set timeout 5

set host [lindex $argv 0]
set daemon [lindex $argv 1]
set password [lindex $argv 2]

set prompt1 "> "
set enable "enable"

set clear_sess "clear bgp *"
spawn telnet $host $daemon

expect "Password:"
send "$password\r"

expect ">"

send "$enable\r"
expect "#"

send "$clear_sess\r"
expect "#"
