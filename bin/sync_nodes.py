#!/bin/env python3

## sync_nodes script
## Simple script to sync folders and files between nodes with rsync via ssh.
## Possibly can also restart systemd services via ssh.

## Requirements
### python3
### ssh
### rsync

# Copyright (c) 2022 Luca Nucifora
# All rights reserved.

# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:

# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.

# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.

# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from
#    this software without specific prior written permission.

# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

## Load libraries

import sys, getopt, logging, datetime, time, getpass, os
import shutil, shlex, subprocess
import yaml

## Prerequisites

# script location
mypath = os.path.dirname(os.path.realpath(__file__))

# system encoding
sys_encod = sys.getdefaultencoding()

# parse script options and arguments
try:
    opts, args = getopt.getopt(sys.argv[1:],'hdfqc:',['help','debug','foreground','quiet','config'])
except:
    print('Wrong options. Abort execution.')
    print(f'''{os.path.basename(__file__)}
    -h | --help          print this help
    [-d | --debug]       log verbose information
    [-f | --foreground]  log to logfile and stdout
    [-q | --quiet]       log only errors
    [-c | --config]      config file path, relative to this script location''')
    exit(1)

# default settings
log_level = "INFO"
debug = foreground = quiet = False
setting_file = f'{mypath}/../conf/settings.yaml'

for (opt, arg) in opts:
    if (opt == '-d') or (opt == '--debug'):
        log_level = "DEBUG"
        debug = True
    if (opt == '-f') or (opt == '--foreground'):
        foreground = True
    if (opt == '-q') or (opt == '--quiet'):
        log_level = "ERROR"
        quiet = True
    if (opt == '-c') or (opt == '--config'):
        setting_file = f'{mypath}/{arg}'
    if (opt == '-h') or (opt == '--help'):
        print(f'''{os.path.basename(__file__)}
    -h | --help          print this help
    [-d | --debug]       log verbose information
    [-f | --foreground]  log to logfile and stdout
    [-q | --quiet]       log only errors
    [-c | --config]      config file path, relative to this script location''')
        exit(0)

# manage log and stdout
def mylog(debug, foreground, quiet, level, message):
    if not foreground:
        if level == "info":
            logging.info(message)
        elif level == "error":
            logging.error(message)
        else:
            logging.debug(message)
    else:
        if level == "info":
            logging.info(message)
            if not quiet:
                print(message)
        elif level == "error":
            logging.error(message)
            print(message)
        else:
            logging.debug(message)
            if debug:
                print(message)

# load settings from file
if os.path.isfile(setting_file):
    with open(setting_file, "r") as f:
        config = yaml.safe_load(f)
else:
    print('Settings file not present. Abort execution')
    exit(1)
if config is None:
    print('Settings file wrongly formatted. Abort execution')
    exit(1)

# log settings
if "log_file" not in config or config["log_file"] == '':
    config["log_file"] = "sync_nodes.log"
log_file_name = f'{mypath}/../log/{datetime.datetime.today().strftime("%Y%m")}-{config["log_file"]}'
logging.basicConfig(filename = log_file_name, level = log_level, format = '%(asctime)s %(message)s', datefmt = '%Y%m%d-%H%M%S')

mylog(debug, foreground, quiet, 'info', '--------')
mylog(debug, foreground, quiet, 'debug', 'Settings file loaded')

# sleep settings
if "sleep-time-folders" not in config or config["sleep-time-folders"] == '':
    config["sleep-time-folders"] = 1
if "sleep-time-services" not in config or config["sleep-time-services"] == '':
    config["sleep-time-services"] = 1

# needed binaries
mylog(debug, foreground, quiet, 'debug', 'Looking for binaries path')
bin_path = {
    'ssh' : shutil.which("ssh"),
    'rsync' : shutil.which("rsync")
}
for key, value in bin_path.items():
    if value is None:
        mylog(debug, foreground, quiet, 'error', f'{key} binary not found. Abort execution\n')
        exit(1)

## Code execution - script starts here

mylog(debug, foreground, quiet, 'info', 'Start execution')

# exit if no nodes present
if config["nodes"] is None:
    mylog(debug, foreground, quiet, 'info', 'Config file has not nodes. Exit\n')
    exit(0)

mylog(debug, foreground, quiet, 'debug', f'Loaded {len(config["nodes"])} nodes')
mylog(debug, foreground, quiet, 'debug', f'Loaded {len(config["folders"])} folders')
if config["enable-services"]:
    mylog(debug, foreground, quiet, 'debug', f'Loaded {len(config["services"])} services')

# start loop for nodes
for id_n, node in config["nodes"].items():
    # manage optional options
    if not "ssh-port" in node:
        node["ssh-port"] = 22
    if not "user" in node:
        node["user"] = getpass.getuser()

    mylog(debug, foreground, quiet, 'info', f'Connecting to {node["address"]}:{node["ssh-port"]} ...')
    # check if connection with shared keys is working
    command = shlex.split(f'{bin_path["ssh"]} -o BatchMode=yes -p {node["ssh-port"]} {node["user"]}@{node["address"]} "ls /dev/null > /dev/null"')
    try:
        conn_check = subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    except:
        mylog(debug, foreground, quiet, 'error', f'... Connection failed. Skipping node {id_n}')
        continue

    if not isinstance(node["folders"], list) or node["folders"] == "all" :
        node["folders"] = list(config["folders"].keys())
    elif isinstance(node["folders"], list):
        pass
    else:
        mylog(debug, foreground, quiet, 'error', f'Wrong folders configuration. Skipping node {id_n}')
        continue

    # start loop for folders
    for id_f, folder in config["folders"].items():
        if id_f in node["folders"]:
            # manage optional options
            if not "rsync-options" in folder or folder["rsync-options"] is None:
                folder["rsync-options"] = ""
            if not "dest" in folder:
                folder["dest"] = folder["path"]

            mylog(debug, foreground, quiet, 'info', f'Syncing {id_f} folder ...')
            # executing rsync command
            command = shlex.split(f'{bin_path["rsync"]} -a -v -e "ssh -o BatchMode=yes -l {node["user"]} -p {node["ssh-port"]}" {folder["rsync-options"]} {folder["path"]} {node["address"]}:{folder["dest"]}')
            try:
                rsync_folder = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding=sys_encod)
            except subprocess.CalledProcessError as e:
                mylog(debug, foreground, quiet, 'error', f'rsync output:\n{e.output}')
                mylog(debug, foreground, quiet, 'error', f'Skipped folder {id_f}')
                continue
            else:
                mylog(debug, foreground, quiet, 'debug', f'rsync output:\n{rsync_folder.stdout}')
                mylog(debug, foreground, quiet, 'info', f'{id_f} successfully synced')

            # sleep between folders
            time.sleep(config["sleep-time-folders"])

    # start loop for services - if enabled
    if config["enable-services"]:
        for id_s, service in config["services"].items():

            mylog(debug, foreground, quiet, 'info', f'Trying service {id_s} {service["method"]} ...')
            
            # manage optional options
            if not "sudo" in service:
                service["sudo"] = False
            
            # restarting|reloading services
            command = shlex.split(f'{bin_path["ssh"]} -q -t -o BatchMode=yes -p {node["ssh-port"]} {node["user"]}@{node["address"]} "{"sudo" if service["sudo"] else ""} systemctl {service["method"]} {service["name"]}; sleep 2; {"sudo" if service["sudo"] else ""} systemctl is-active {service["name"]}"')
            try:
                re_service = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding=sys_encod)
            except subprocess.CalledProcessError as e:
                mylog(debug, foreground, quiet, 'debug', f'command output:\n{e.output}')
                mylog(debug, foreground, quiet, 'error', f'... something went wrong. Please check on {id_n} system')
                continue
            else:
                mylog(debug, foreground, quiet, 'debug', f'command output:\n{re_service.stdout}')
                mylog(debug, foreground, quiet, 'info', f'{id_s} successfully {service["method"]}ed')

            # sleep between services
            time.sleep(config["sleep-time-services"])


mylog(debug, foreground, quiet, 'info', 'End execution\n')
exit(0)
