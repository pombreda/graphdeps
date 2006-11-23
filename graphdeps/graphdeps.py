#!/usr/bin/env python
# graphdeps.py
#
# Generate a dot file for graphviz with the library dependencies of a ELF
# binary.
#
# Copyright (C) 2006 Instituto Nokia de Tecnologia
#                    Osvaldo Santana Neto <osvaldo.santana@indt.org.br>
#                    Gustavo Sverzut Barbieri <gustavo.barbieri@indt.org.br>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
#

import os
import sys
import re
from optparse import OptionParser

from subprocess import *

def run(cmd):
    try:
        p = Popen(cmd, shell=True,
                stdin=PIPE, stdout=PIPE, stderr=PIPE,
                close_fds=True
            )
    except Exception, e:
        print >>sys.stderr, "ERROR: running %s (%s)" % (cmd, e)
        raise SystemExit

    return p.stdout.readlines(), p.stderr.read().strip()

def libname(path):
    path = os.path.basename(path)
    pieces = []
    path = path.split('.')
    path.reverse()
    skip = True
    for e in path:
        if e == "so":
            skip = False
        elif skip and e.isdigit():
            continue
        else:
            pieces.append(e)
    pieces.reverse()
    path = '.'.join(pieces)
    if path.startswith("lib"):
        path = path[3:]
    return path

class Lib(object):
    lib_index = {}
    path_dict = {}
    def __init__(self, filename, ignore_list, max_level, parent = None):
        self.filename = filename
        self.parent = parent

        if self.parent is None:
            self.level = 0
        else:
            self.level = self.parent.level + 1

        self.children = []
        if self.level < max_level:
            self.load_children(ignore_list, max_level)

    def load_children(self, ignore_list, max_level):
        out, err = run("ldd %s" % (self.filename))
        for line in out:
            splited_line = [ x for x in line.split()[:-1] if "=>" not in x ]
            Lib.path_dict[splited_line[0]] = splited_line[len(splited_line) == 2]

        out, err = run("readelf -d %s" % (Lib.path_dict.get(self.filename, self.filename)))

        libname_re = re.compile("^.*Shared library: \[(?P<f>.*)\]$")

        for line in out:
            match = libname_re.search(line.strip())
            if match is None:
                continue

            filename = match.groupdict()['f']

            if [ i for i in ignore_list if re.match(i, filename) is not None ]:
                continue

            try:
                lib = Lib.lib_index[filename]
            except KeyError, e:
                lib = Lib(filename, ignore_list, max_level, self)
                Lib.lib_index[filename] = lib


            self.children.append(lib)


    def dependencies(self):
        ret = set()
        name = libname(self.filename)
        for child in self.children:
            ret.add('"%s" -> "%s"' % (name, libname(child.filename)))
            ret = ret.union(child.dependencies())
        return ret


if __name__ == "__main__":
    depth = 3
    ignore_list = [ 'libc.so', 'libm.so', 'libdl.so', 'libz.so',
                    'libresolv.so', 'libpthread.so', 'librt.so', 'libnsl.so' ]

    parser = OptionParser()
    parser.add_option("-i", "--ignore", dest="ignore_list", action="append",
                      metavar="LIBRARY", default=ignore_list,
                      help="library to ignore, maybe be used multiple times.")
    parser.add_option("-d", "--depth", dest="depth", type="int",
                      default=depth,
                      help="recursion depth to graph.")
    parser.add_option("-o", "--outfile", dest="outfile", metavar="FILE",
                      help="output file, use '-' for stdout.")

    options, args = parser.parse_args()

    ignore_list = options.ignore_list
    depth = options.depth

    input_libs = []
    for input_file in args:
        input_libs.append(Lib(input_file, ignore_list, depth))

    deps = set()
    for x in input_libs:
        deps = deps.union(x.dependencies())

    if deps:
        if options.outfile and options.outfile.strip() != '-':
            fd = open(options.outfile, "w")
        else:
            fd = sys.stdout

        fd.write("digraph G {\n")
        for x in deps:
            fd.writelines((x, "\n"))
        fd.write("}\n")

