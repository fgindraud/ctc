# Copyright (c) 2015 Francois GINDRAUD
# 
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
# 
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import os
import sys
import argparse
import json
import subprocess
import tempfile

import grako.buffering
import grako.exceptions

from . import template
from . import printer
from . import parser

class CubicleBuffer (grako.buffering.Buffer):
    """
    Grako Buffer subclass used to remove the caml-style recursive comments in cubicle.
    """
    def eat_comments (self):
        """
        Override the grako eat_comments function.
        Removes comments starting at current buffer position.
        """
        if self.match ("(*"):
            level = 1
            while level > 0:
                matched = self._scanre ("(?:.|\n)*?(\(\*|\*\))") # match next '(*' or '*)'
                if not matched:
                    raise grako.exceptions.ParseError ("Unmatched comment at line {}".format (self.line_info ().line + 1))
                if matched.group (1) == "(*":
                    level += 1
                if matched.group (1) == "*)":
                    level -= 1
                self.move (len (matched.group (0)))

class Compiler:
    """
    Cubicle Template Compiler frontend class.
    """
    def __init__ (self, cin):
        """
        Create a compiler by reading a template AST from file-like object cin.
        """
        p = parser.CubicleParser (parseinfo = True)
        buf = CubicleBuffer (cin.read ())
        ast = p.parse (buf, "model")
        self.engine = template.TemplateEngine (ast)

    def run (self, cout, data):
        """
        Compiles the template AST with the given data.

        Steps :
        * Instantiate template AST using data,
        * Convert "extended syntax" elements to conventionnal Cubicle syntax,
        * Print the result in cout file-like object.

        Data must be a tree of dict-like or list-like objects.
        Data format must match what templates statement require in the input AST.
        No data is a valid input ; there must be no template statements, and only extended syntax conversion will be performed.
        """
        printer.ExpandedAstPrinter ().write (cout, self.engine.run (data))


class CompilerOutput:
    """
    Represent a compiler output stream.
    * a regular file, kept after compilation
    * a temporary file, destroyed at end of script
    * stdout, untouched
    """
    def __init__ (self, file_obj, name = None, is_tmp = False):
        self.obj = file_obj
        self.name = name
        self.is_tmp = is_tmp
    def close (self):
        if self.obj != sys.stdout and not self.obj.closed:
            self.obj.close ()
    def destroy (self):
        self.close ()
        if self.is_tmp:
            os.unlink (self.name)
    @staticmethod
    def from_file (filename):
        return CompilerOutput (open (filename, "w"), filename)
    @staticmethod
    def from_stdout ():
        return CompilerOutput (sys.stdout)
    @staticmethod
    def from_tempfile ():
        fd, filename = tempfile.mkstemp (suffix = ".cub")
        return CompilerOutput (open (fd, "w"), filename, is_tmp = True)

def main ():
    """
    Script interface entry point.

    Reads the commandline arguments to perform compilation and maybe call cubicle on the compiled file.
    """
    parser = argparse.ArgumentParser ( prog = "ctc",
            description = "Cubicle Template Compiler")
    parser.add_argument ("-c", "--compile",
            action = "store_true",
            help = "compile only ; do not start cubicle")
    parser.add_argument ("-d", "--data", 
            type = argparse.FileType ("r"),
            metavar = "DATA",
            help = "json data file (default = no data)")
    parser.add_argument ("-f", "--file",
            type = argparse.FileType ("r"), default = sys.stdin,
            metavar = "CUB",
            help = "cubicle template file (default = stdin)")
    parser.add_argument ("-o", "--output",
            metavar = "OUT",
            help = "filename to store compiled output (default = stdout if -c, not stored if not -c)")
    parser.add_argument ("cubicle_args", nargs = argparse.REMAINDER,
            metavar = "CUBICLE_ARGS",
            help = "arguments to pass to cubicle ; put them after -- in case of conflict")
    args = parser.parse_args ()
   
    # Load data
    data = {}
    if args.data:
        data = json.load (args.data)

    # Load AST
    compiler = Compiler (args.file)

    # Compiled file management : output always overrides
    if args.output: compiled_file = CompilerOutput.from_file (args.output)
    else:
        if args.compile: compiled_file = CompilerOutput.from_stdout ()
        else: compiled_file = CompilerOutput.from_tempfile ()

    try:
        # Compile
        compiler.run (compiled_file.obj, data)
        compiled_file.close ()
        
        if not args.compile:
            # Run cubicle
            cub_arg = args.cubicle_args
            if len (cub_arg) > 0 and cub_arg[0] == "--":
                del cub_arg[0]
            cub_arg = ["cubicle"] + cub_arg + [compiled_file.name]
            print ("Running", " ".join (cub_arg), file = sys.stderr)
            return subprocess.call (cub_arg, stdin = subprocess.DEVNULL, stderr = subprocess.STDOUT)
    finally:
        compiled_file.destroy ()

