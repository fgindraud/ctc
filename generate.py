#!/usr/bin/env python
from template import TemplateEngine
import sys

data = {
        "T": [
            "A",
            "B"
            ],
        "R": {
            "a": { "size": 43 },
            "b": { "size": 42 }
            }
        }

TemplateEngine (sys.stdin).run (sys.stdout, data)

