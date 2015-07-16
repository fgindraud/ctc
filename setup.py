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

from setuptools import setup
from setuptools.command.build_py import build_py
import io
import sys
import os
import inspect

class CustomBuildPy (build_py):
    """ Modify the build command to generate the parser too """
    def run (self):
        # Get paths for parser files
        setup_script_path = os.path.dirname (inspect.getfile (CustomBuildPy))
        generate_parser_cmd = "{} -m grako -m Cubicle -o {} {}".format (
                sys.executable,
                os.path.join (setup_script_path, "ctc", "parser.py"),
                os.path.join (setup_script_path, "ctc", "cubicle.ebnf"))
        print (generate_parser_cmd, file = sys.stderr)
        if os.system (generate_parser_cmd) != 0:
            raise Exception ("parser generation failed")
        # Build as usual
        build_py.run (self)

setup (
        # Base info
        name = "ctc",
        version = "0.1",
        author = "François GINDRAUD",
        author_email = "francois.gindraud@gmail.com",

        # Code content
        packages = ["ctc"],
        entry_points = {
            "console_scripts" : [
                "ctc = ctc:main"
                ]
            },
        cmdclass = {
            "build_py": CustomBuildPy
            },

        # Metadata
        description = "Cubicle Template Compiler",
        long_description = io.open ("Readme.md", encoding = "utf-8").read (),
        url = "https://github.com/lereldarion/ctc",
        license = "MIT",

        # Classification
        classifiers = [
            "Development Status :: 4 - Beta",
            "License :: OSI Approved :: MIT License",
            "Intended Audience :: Developers",
            "Intended Audience :: Science/Research",
            "Operating System :: Unix",
            "Programming Language :: Python :: 3",
            "Topic :: Software Development :: Code Generators",
            "Topic :: Software Development :: Compilers",
            "Topic :: Software Development :: Interpreters",
            "Topic :: Text Processing :: General"
            ]
        )

