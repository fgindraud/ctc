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

class CommonExprPrinter:
    """
    Collections of printer functions for expression AST nodes that are independent of expansion.
    These functions take an AST node, and recursively compute the string representation of it.
    """
    def array (self, a):
        return "{}[{}]".format (self.name (a.name), ", ".join (map (self.name, a.index)))
    def ref (self, s):
        if s.array is not None: return self.array (s.array)
        if s.var is not None: return self.name (s.var.name)
    def rvalue (self, v):
        if v.ref is not None: return self.ref (v.ref)
        if v.const is not None: return v.const
    def expr (self, e):
        if e.val is not None: return self.rvalue (e.val)
        if e.op is not None: return "{} {} {}".format (self.rvalue (e.lhs), e.op, self.rvalue (e.rhs))
    def comp_expr (self, c):
        return "{} {} {}".format (self.expr (c.lhs), c.op, self.expr (c.rhs))
    def forall_expr (self, f):
        if f.comp is not None: return "forall_other {}. {}".format (f.proc, self.comp_expr (f.comp))
        if f.expr is not None: return "forall_other {}. ({})".format (f.proc, self.or_expr (f.expr))
    def bool_expr (self, e):
        if e.forall is not None: return self.forall_expr (e.forall)
        if e.comp is not None: return self.comp_expr (e.comp)
    
    def and_expr (self, a):
        """ An AND expression is a list of AND elements, with && operators in between. """
        return " && ".join (map (self.and_elem, a))
    def or_expr (self, o):
        """ An OR expression is a list of OR elements, with || operators in between. """
        return " || ".join (map (self.or_elem, o))

class TemplateExprPrinter (CommonExprPrinter):
    """
    Collections of printer functions for expression AST nodes before expansion (with templates statements).
    These functions complete the ones in CommonExprPrinter to support all unexpanded AST expressions.
    """
    def template (self, t):
        """ A template element. """
        if t.arg is not None: return t.arg
        if t.key_ref is not None: return t.key_ref
        if t.field_ref is not None: return "{}.{}".format (t.field_ref.key, t.field_ref.field)
    def template_args (self, a):
        return ", ".join (map (self.template, a))
    def template_decl (self, d):
        """ Unexpanded : template declarations are present in statements and template iterators. """
        if d.cond is not None:
            return "@{} | {}@".format (self.template_args (d.args), self.or_expr (d.cond))
        else: return "@{}@".format (self.template_args (d.args))
    def name (self, n):
        """ Unexpanded : names are interleaved lists of name parts and template elements. """
        name_parts = n[:]
        name_parts[1::2] = map (self.template, name_parts[1::2])
        return "@".join (name_parts)
    def and_elem (self, e):
        """ Unexpanded : AND elements can be boolean expressions, template AND iterators, or nested OR expression. """
        if e.expr is not None: return self.bool_expr (e.expr)
        if e.template is not None: return "{} (&& {})".format (
                self.template_decl (e.template.decl), self.and_expr (e.template.expr))
        if e.or_expr is not None: return "({})".format (self.or_expr (e.or_expr))
    def or_elem (self, e):
        """ Unexpanded : OR elements can be AND expressions, or template OR iterators. """
        if e.expr is not None: return self.and_expr (e.expr)
        if e.template is not None: return "{} (|| {})".format (
                self.template_decl (e.template.decl), self.and_expr (e.template.expr))

class ExpandedExprPrinter (CommonExprPrinter):
    """
    Collections of printer functions for expression AST nodes after expansion (without template statements).
    These functions complete the ones in CommonExprPrinter to support all expanded AST expressions.
    """
    def name (self, n):
        """ Expanded : names are simple strings. """
        return n
    def and_elem (self, e):
        """ Expanded : AND elements are inline boolean expressions. """
        return self.bool_expr (e)
    def or_elem (self, e):
        """ Expanded : OR elements are inline AND expressions (list of AND elements). """
        return self.and_expr (e)

class ExpandedAstPrinter (ExpandedExprPrinter):
    """
    Complete printer for expanded AST.
    """
    def write (self, stream, ast):
        """
        Print string representation of expanded AST ast in stream file-like object.
        Relies in ExpandedExprPrinter functions, but is a single big function (not modular).
        """
        def line (fmt, *args):
            stream.write (fmt.format (*args) + "\n")
        def line_proc_expr_construct (s, name):
            """ Common printer for init, unsafe, invariant constructs (they have a similar structure). """
            line ("{} ({}) {{ {} }}", name, " ".join (s.procs), self.or_expr (s.expr))

        if ast.size_proc is not None:
            line ("number_procs {}", ast.size_proc)
        for t in ast.types:
            if t.enum is not None:
                line ("type {} = {}", t.name, " | ".join (t.enum));
            else:
                line ("type {}", t.name)
        for d in ast.decls:
            line ("{} {} : {}", d.kind, self.ref (d.name), d.typename)
        line_proc_expr_construct (ast.init, "init")
        for i in ast.invariants:
            line_proc_expr_construct (i, "invariant")
        for u in ast.unsafes:
            line_proc_expr_construct (u, "unsafe")
        for t in ast.transitions:
            line ("transition {} ({})", t.name, " ".join (t.procs))
            if t.require is not None:
                line ("\trequires {{ {} }}", self.or_expr (t.require))
            line ("{{")
            for u in t.updates:
                if u.rhs.switch is not None:
                    line ("\t{} := case", self.ref (u.lhs))
                    for c in u.rhs.switch:
                        if c.cond == "_":
                            line ("\t\t| _ : {}", self.expr (c.expr))
                        else:
                            line ("\t\t| {} : {}", self.and_expr (c.cond), self.expr (c.expr))
                    line ("\t;")
                if u.rhs.expr is not None:
                    line ("\t{} := {};", self.ref (u.lhs), self.expr (u.rhs.expr))
                if u.rhs.rand is not None:
                    line ("\t{} := ?;", self.ref (u.lhs))
            line ("}}")

