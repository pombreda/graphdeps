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
from fnmatch import fnmatch
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
    libname_re = re.compile("^\s0x\w+\s\(NEEDED\)\s+Shared library:\s+\[(?P<libname>[^]]+)\]\s*$")
    ldd_re = re.compile("^\s+(?P<libname>\S+)\s+=>\s+(?P<libpath>[^(]*)\s+\(0x\w+\)\s+$")

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
            match = self.ldd_re.search(line)
            if match is None:
                path = name = line.split()[0]
            else:
                name = match.groupdict()["libname"]
                path = match.groupdict()["libpath"]
                if not path or path == "not found":
                    path = name
            Lib.path_dict[name] = path

        path = Lib.path_dict.get(self.filename, self.filename)
        out, err = run("readelf -W -d %s" % path)

        for line in out:
            match = self.libname_re.search(line)
            if match is None:
                continue

            name = match.groupdict()['libname']
            path = Lib.path_dict.get(name, None)
            if not path:
                if name.startswith("ld-linux.so"):
                    continue
                print >> sys.stderr, "Unknow library path: %r" % name
                path = name


            for ignore in ignore_list:
                if fnmatch(path, ignore) or fnmatch(name, ignore):
                    break
            else:
                # It's not ignored, add child
                try:
                    lib = Lib.lib_index[path]
                except KeyError, e:
                    lib = Lib(path, ignore_list, max_level, self)
                    Lib.lib_index[path] = lib

                self.children.append(lib)


    def dependencies(self):
        ret = set()
        for child in self.children:
            ret.add((self.filename, child.filename))
            ret = ret.union(child.dependencies())
        return ret


if __name__ == "__main__":
    depth = 10
    ignore_list = ["libc.so*"]

    parser = OptionParser()
    parser.add_option("-i", "--ignore", dest="ignore_list", action="append",
                      metavar="LIBRARY", default=ignore_list,
                      help=("Library to ignore, maybe be used multiple times. "
                            "It does UNIX filename pattern matching."))
    parser.add_option("-d", "--depth", dest="depth", type="int",
                      default=depth,
                      help="Recursion depth to graph.")
    parser.add_option("-o", "--outfile", dest="outfile", metavar="FILE",
                      help="Output file, use '-' for stdout.")
    parser.add_option("-f", "--full-names", action="store_true",
                      dest="full_names", default=False,
                      help="Use full library names.")
    parser.add_option("-b", "--base-names", action="store_true",
                      dest="base_names", default=False,
                      help=("Use just basename (not whole path) if " \
                            "--full-names is in use."))

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
        fd.write("\t/* presentation settings */\n")
        libs = set()
        for a, b in deps:
            libs.add(a)
            libs.add(b)
        for lib in libs:
            extra = ""
            basename = os.path.basename(lib)
            for inlib in input_libs:
                if basename == os.path.basename(inlib.filename):
                    extra = ", style=\"filled\""
                    break
            if options.full_names:
                if options.base_names:
                    name = basename
                else:
                    name = lib
            else:
                name = libname(lib)
            fd.write("\t\"%s\" [label=\"%s\"%s];\n" % (lib, name, extra))

        fd.write("\n\t/* dependencies */\n")
        for x in deps:
            fd.write("\t\"%s\" -> \"%s\";\n" % x)
        fd.write("}\n")

