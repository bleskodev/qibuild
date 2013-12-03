## Copyright (c) 2012, 2013 Aldebaran Robotics. All rights reserved.
## Use of this source code is governed by a BSD-style license that can be
## found in the COPYING file.

""" Tools to deploy files to remote targets"""

import urlparse
import os

from collections import OrderedDict

from qisys import ui
import qisys.command
import qibuild.deploy

FILE_SETUP_GDB  = """\
# gdb script generated by qiBuild

set architecture i386
set verbose
set sysroot %(sysroot)s
set solib-search-path %(solib_search_path)s
"""

FILE_SETUP_TARGET_GDB  = """\
# gdb script generated by qiBuild

source %(source_file)s
target remote %(remote_gdb_address)s
"""

FILE_REMOTE_GDBSERVER_SH = """\
#!/bin/bash
# script generated by qiBuild
# run a gdbserver on the remote target

here=$(cd $(dirname $0) ; pwd)

if [ "$#" -lt "1" ] ; then
  echo "please specify the binary to run"
  exit 1
fi

binary=$1
shift 1
echo ""
echo "To connect to this gdbserver launch the following command in another terminal:"
echo "  %(gdb)s -x \"${here}/setup_target.gdb\" \"${here}/${binary}\""
echo ""

#echo ssh -p %(port)s %(remote)s -- gdbserver %(gdb_listen)s "%(remote_dir)s/${1}"
ssh -p %(port)s %(remote)s -- gdbserver %(gdb_listen)s "%(remote_dir)s/${binary} $*"
"""

def parse_url(remote_url):
    """ Parse a remote url

    Return a dict with the following keys:
    * ``given`` : the remote url that was given
    * ``login`` : the username to log with
    * ``dir``   : the directory on the server
    * ``url``   : the name of the server

    Note that the if the user plays with the "hostname" option in its
    .ssh/config, the "server" part might not be a valid hostname. In such a
    case, the deploy will work (thanks to ssh) but the remote debugging will
    not.

    """
    if "@" not in remote_url:
        return None

    login = ''
    url   = ''
    port  = None
    dir   = ''

    o = urlparse.urlparse(remote_url)
    if o.scheme == "ssh":
        login = o.username
        url = o.hostname
        dir = o.path
        port = o.port
    elif o.scheme is not "":
        # Scheme not supported
        return None
    else:
        parts = remote_url.split('@', 1)
        if len(parts) == 1:
            url = parts[0]
        elif len(parts) == 2:
            login = parts[0]
            url   = parts[1]

        parts = url.split(':', 1)
        url = parts[0]
        if len(parts) == 2:
            dir = parts[1]

    ret = {'given':remote_url, 'login':login, 'url':url, 'dir':dir}
    if port is not None:
        ret["port"] = port
    return ret

def deploy(local_directory, remote_url, port=22, use_rsync=True, filelist=None):
    """Deploy a local directory to a remote url."""
    parts = parse_url(remote_url)
    if not parts.has_key("port"):
        parts["port"]=port
    # ensure destination directory exist before deploying data
    if len(remote_url.split(":")) > 1:
        cmd = ["ssh", "-p", str(parts["port"]), parts["login"]+"@"+parts["url"], "mkdir", "-p",
                parts["dir"]]
        qisys.command.call(cmd)
    if use_rsync:
        # This is required for rsync to do the right thing,
        # otherwise the basename of local_directory gets
        # created
        local_directory = local_directory + "/."
        cmd = ["rsync",
            "--recursive",
            "--links",
            "--perms",
            "--times",
            "--specials",
            "--progress", # print a progress bar
            "--checksum", # verify checksum instead of size and date
            "--exclude=.debug/",
            "-e", "ssh -p %d" % parts["port"], # custom ssh port
            local_directory, parts["login"]+"@"+parts["url"]+":"+parts["dir"]
        ]
        if filelist:
            cmd.append("--files-from=%s" % filelist)
    else:
        # Default to scp
        cmd = ["scp", "-P", str(port), "-r", local_directory, remote_url]
    qisys.command.call(cmd)

def _generate_setup_gdb(dest, sysroot="\"\"", solib_search_path=[], remote_gdb_address=""):
    """ generate a script that connect a local gdb to a gdbserver """
    source_file = os.path.abspath(os.path.join(dest, "setup.gdb"))
    with open(source_file, "w+") as f:
        f.write(FILE_SETUP_GDB % { 'sysroot'            : sysroot,
                                   'solib_search_path'  : ":".join(solib_search_path)
                                 })
    with open(os.path.join(dest, "setup_target.gdb"), "w+") as f:
        f.write(FILE_SETUP_TARGET_GDB % { 'source_file'        : source_file,
                                          'remote_gdb_address' : remote_gdb_address
                                        })


def _generate_run_gdbserver_binary(dest, remote, gdb, gdb_listen, remote_dir, port):
    """ generate a script that run a program on the robot in gdbserver """
    if remote_dir == "":
        remote_dir = "."
    remote_gdb_script_path = os.path.join(dest, "remote_gdbserver.sh")
    with open(remote_gdb_script_path, "w+") as f:
        f.write(FILE_REMOTE_GDBSERVER_SH % { 'remote': remote,
                                             'gdb_listen': gdb_listen,
                                             'remote_dir': remote_dir,
                                             'gdb': gdb,
                                             'port': port})
    os.chmod(remote_gdb_script_path, 0755)
    return remote_gdb_script_path

def _get_subfolder(directory):
    res = list()
    for root, dirs, files in os.walk(directory):
        new_root = os.path.abspath(root)
        if not os.path.basename(new_root).startswith(".debug"):
            res.append(new_root)
    return res


def _generate_solib_search_path(cmake_builder, project_name):
    """ generate the solib_search_path useful for gdb """
    res = list()
    dep_types = ["build", "runtime"]
    build_worktree = cmake_builder.build_worktree
    project = build_worktree.get_build_project(project_name)
    deps_solver = cmake_builder.deps_solver
    dep_projects = deps_solver.get_dep_projects([project], dep_types)
    for dep_project in dep_projects:
        dep_build_dir = dep_project.build_directory
        dep_lib_dir = os.path.join(dep_build_dir, "deploy", "lib")
        res.extend(_get_subfolder(dep_lib_dir))
    dep_packages = deps_solver.get_dep_packages([project], dep_types)
    for dep_package in dep_packages:
        dep_lib_dir = os.path.join(dep_package.path, "lib")
        res.extend(_get_subfolder(dep_lib_dir))
    # Idiom to sort an iterable preserving order
    return list(OrderedDict.fromkeys(res))

def generate_debug_scripts(cmake_builder, project_name, url, port=22):
    """ generate all scripts needed for debug """
    # FIXME: rewrite this to support several urls
    return
    (remote, server, remote_directory) = qibuild.deploy.parse_url(url)

    build_worktree = cmake_builder.build_worktree
    project = build_worktree.get_build_project(project_name)
    destdir = os.path.join(project.build_directory, "deploy")

    solib_search_path = _generate_solib_search_path(cmake_builder, project_name)
    sysroot = None
    gdb = None
    message = None
    toolchain = cmake_builder.toolchain
    if toolchain:
        sysroot = toolchain.get_sysroot()
    if sysroot:
        # assume cross-toolchain
        gdb = toolchain.get_cross_gdb()
        if gdb:
            message = "Cross-build. Using the cross-debugger provided by the toolchain."
        else:
            message = "Remote debugging not available: No cross-debugger found in the cross-toolchain"
    else:
        # assume native toolchain
        sysroot = "\"\""
        gdb = qisys.command.find_program("gdb")
        if gdb:
            message = "Native build. Using the debugger provided by the system."
        else:
            message = "Debugging not available: No debugger found in the system."
    if not gdb:
        ui.warning(message)
        return None
    if toolchain:
        sysroot=toolchain.get_sysroot()
    _generate_setup_gdb(destdir, sysroot=sysroot,
                        solib_search_path=solib_search_path,
                        remote_gdb_address="%s:2159" % server)
    gdb_script = _generate_run_gdbserver_binary(destdir, gdb=gdb, gdb_listen=":2159",
                                                remote=remote, port=port,
                                                remote_dir=remote_directory)

    ui.info(message)
    return gdb_script
