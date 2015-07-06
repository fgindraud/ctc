#!/usr/bin/env python

import sys

# Generate the parser if not found
try:
    import cubicle_parser
except ImportError:
    import os
    os.system ("python -m grako -m Cubicle -o cubicle_parser.py cubicle.ebnf")
    import cubicle_parser

class CubicleBuffer:
    # to remove recursive comments, TODO
    def eat_comments ():
        pass

class TemplateEngine:
    def __init__ (self, cin):
        parser = cubicle_parser.CubicleParser ()
        self.ast = parser.parse (cin.read (), "model")

    def run (self, cout, data):
        self.output_ast (cout, self.substitute (data))

    def substitute (self, data):
        return self.ast # make substitutions

    def output_ast (self, stream, ast):
        def write (fmt, *args):
            stream.write (fmt.format (*args) + "\n")

        def ref (s):
            if s.array is not None: return s.array.name + "[" + ", ".join (s.array.index) + "]"
            if s.var is not None: return s.var.name
        def rvalue (v):
            if v.ref is not None: return ref (v.ref)
            if v.const is not None: return v.const
        def expr (e):
            if e.val is not None: return rvalue (e.val)
            if e.op is not None: return "{} {} {}".format (rvalue (e.lhs), e.op, rvalue (e.rhs))
        def comp_expr (c):
            return "{} {} {}".format (expr (c.lhs), c.op, expr (c.rhs))
        def forall_expr (f):
            if f.comp is not None: return "forall_other {}. {}".format (f.name, comp_expr (f.comp))
            if f.expr is not None: return "forall_other {}. ({})".format (f.name, or_expr (f.expr))
        def bool_expr (e):
            if e.forall is not None: return forall_expr (e.forall)
            if e.comp is not None: return comp_expr (e.comp)
        def and_expr (a):
            return " && ".join (bool_expr (e) for e in a)
        def or_expr (o):
            return " || ".join (and_expr (a) for a in o)
        
        def write_proc_expr_construct (s, name):
            write ("{} ({}) {{ {} }}", name, " ".join (s.procs), or_expr (s.expr))

        if ast.size_proc is not None:
            write ("number_procs {}", ast.size_proc)
        for t in ast.types:
            if t.enum is not None:
                write ("type {} = {}", t.name, " | ".join (t.enum));
            else:
                write ("type {}", t.name)
        for d in ast.decls:
            write ("{} {} : {}", d.kind, ref (d.name), d.typename)
        write_proc_expr_construct (ast.init, "init")
        for i in ast.invariants:
            write_proc_expr_construct (i, "invariant")
        for u in ast.unsafes:
            write_proc_expr_construct (u, "unsafe")
        for t in ast.transitions:
            write ("transition {} ({})", t.name, " ".join (t.procs))
            if t.require is not None:
                write ("\trequires {{ {} }}", or_expr (t.require))
            write ("{{")
            for u in t.updates:
                if u.rhs.switch is not None:
                    write ("\t{} := case", ref (u.lhs))
                    for c in u.rhs.switch:
                        if c.cond == "_":
                            write ("\t\t| _ : {}", expr (c.expr))
                        else:
                            write ("\t\t| {} : {}", and_expr (c.cond), expr (c.expr))
                    write ("\t;")
                if u.rhs.expr is not None:
                    write ("\t{} := {};", ref (u.lhs), expr (u.rhs.expr))
                if u.rhs.rand is not None:
                    write ("\t{} := ?;", ref (u.lhs))
            write ("}}")

engine = TemplateEngine (sys.stdin)
engine.run (sys.stdout, {})

