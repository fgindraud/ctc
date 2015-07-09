#!/usr/bin/env python
from template import CubicleTemplateCompiler, TemplateError
import sys

data = {
        "T": {
            "A": {
                "dep": [],
                "access": "RW"
                },
            "B": {
                "dep": ["A"],
                "access": "RO"
                }
            }
        }

# will need cond

try: CubicleTemplateCompiler (sys.stdin).run (sys.stdout, data)
except TemplateError as e: print ("TemplateError: {}".format (e), file=sys.stderr)

