#!/usr/bin/env python
from template import CubicleTemplateCompiler, TemplateError
import sys

data = {
        "Tasks": {
            "A": {
                "dep": [],
                "accesses": {
                    0: dict(mode = "C")
                    }
                },
            "B": {
                "dep": ["A"],
                "accesses": {
                    0: dict (mode = "RW", read = "D_A")
                    }
                },
            "C": {
                "dep": ["B"],
                "accesses": {
                    0: dict (mode = "RO", read = "D_B")
                    }
                }
            },
        "Regions": range (1)
        }

try: CubicleTemplateCompiler (sys.stdin).run (sys.stdout, data)
except TemplateError as e: print ("TemplateError: {}".format (e), file=sys.stderr)

