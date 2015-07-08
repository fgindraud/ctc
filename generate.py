#!/usr/bin/env python
from template import TemplateEngine, TemplateError
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

try: TemplateEngine (sys.stdin).run (sys.stdout, data)
except TemplateError as e: print ("TemplateError: {}".format (e), file=sys.stderr)

