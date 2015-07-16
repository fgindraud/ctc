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

from .compiler import Compiler

__all__ = ["Compiler"]

def main ():
    import os
    import sys
    import argparse
    import json
    import grako.exceptions
    import subprocess
    import tempfile
    from . import template
    
    parser = argparse.ArgumentParser (prog = "ctc",
            description = "cubicle template compiler")
    parser.add_argument ("-c", "--compile",
            action = "store_true",
            help = "output the intermediate cubicle file and stops")
    parser.add_argument ("-d", "--data", 
            type = argparse.FileType ("r"),
            metavar = "DATA",
            help = "json data file (default = no data)")
    parser.add_argument ("-f", "--file",
            type = argparse.FileType ("r"), default = sys.stdin,
            metavar = "CUB",
            help = "cubicle template file (default = stdin)")
    parser.add_argument ("-o", "--output",
            type = argparse.FileType ("w"), default = sys.stdout,
            metavar = "OUT",
            help = "filename to store output (default = stdout)")
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

    if args.compile:
        # Compile to output
        compiler.run (args.output, data)
        return 0
    else:
        # Generate temporary file, as cubicle requires a file.cub as input
        compiled_file_fd, compiled_file_name = tempfile.mkstemp (suffix = ".cub")
        try:
            # Compile
            with open (compiled_file_fd, "w") as tmpfile:
                compiler.run (tmpfile, data)

            # Run cubicle
            cub_arg = args.cubicle_args
            if len (cub_arg) > 0 and cub_arg[0] == "--":
                del cub_arg[0]
            cub_arg = ["cubicle"] + cub_arg + [compiled_file_name]
            print ("Running", " ".join (cub_arg), file = sys.stderr)
            return subprocess.call (cub_arg, stdout = args.output)
        finally:
            # Ensure deletion
            os.unlink (compiled_file_name)

if __name__ == "__main__":
    main ()

