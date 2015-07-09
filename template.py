#!/usr/bin/env python

import sys
import collections
import re
import operator

# Get grako libraries
try:
    import grako.buffering
    import grako.exceptions
    import grako.ast
except ImportError:
    sys.stderr.write ("grako python module not found, please install it\n")
    raise

# Generate the parser if not found
try:
    import cubicle_parser
except ImportError:
    import os
    os.system ("python -m grako -m Cubicle -o cubicle_parser.py cubicle.ebnf")
    import cubicle_parser

__all__ = ["CubicleTemplateCompiler", "TemplateError"]

# Utils
NAME_FORMAT = re.compile ("^[A-Za-z][A-Za-z0-9_]*$")

def line_number (ast_node):
    return ast_node.parseinfo.buffer.line_info (ast_node.parseinfo.pos).line + 1

class TemplateError (Exception):
    pass

def alter (node, **kwargs):
    """ copy and update AST node with new args """
    new = dict (node)
    new.update (**kwargs)
    return grako.ast.AST (new)
def alter_f (node, context, **funcs):
    """
    Fast copy and update for expressions, calls f(key, context) for all given key=f
    If f returns None, returns None (recursively delete empty constructs)
    """
    new = dict (node)
    for field, func in funcs.items ():
        new[field] = func (node[field], context)
        if new[field] is None:
            return None
    return grako.ast.AST (new)
def simplify (l, keep_list = False):
    """ Removes None's elements in a list, and returns None if empty """
    cleaned = [e for e in l if e is not None]
    return cleaned if len (cleaned) > 0 or keep_list else None

# Custom buffer to remove caml-style comments
class CubicleBuffer (grako.buffering.Buffer):
    """ Handles removing the caml-style recursive comments in cubicle """
    def eat_comments (self):
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

# Ast expression printing
class CommonExprPrinter:
    """ Collections of str(expr) functions independent of expansion """
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
        if f.comp is not None: return "forall_other {}. {}".format (f.name, self.comp_expr (f.comp))
        if f.expr is not None: return "forall_other {}. ({})".format (f.name, self.or_expr (f.expr))
    def bool_expr (self, e):
        if e.forall is not None: return self.forall_expr (e.forall)
        if e.comp is not None: return self.comp_expr (e.comp)
    
    def and_expr (self, a):
        return " && ".join (map (self.and_elem, a))
    def or_expr (self, o):
        return " || ".join (map (self.or_elem, o))

class TemplateExprPrinter (CommonExprPrinter):
    """ Collections of str(expr) functions for an ast before expansion """
    def template (self, t):
        if t.arg is not None: return t.arg
        if t.key_ref is not None: return t.key_ref
        if t.field_ref is not None: return "{}.{}".format (t.field_ref.key, t.field_ref.field)
    def template_args (self, a):
        return ", ".join (map (self.template, a))
    def template_decl (self, d):
        if d.cond is not None:
            return "@{} | {}@".format (self.template_args (d.args), self.or_expr (d.cond))
        else: return "@{}@".format (self.template_args (d.args))
    def name (self, n): # template name
        name_parts = n[:]
        name_parts[1::2] = map (self.template, name_parts[1::2])
        return "@".join (name_parts)
    def and_elem (self, e):
        if e.expr is not None: return self.bool_expr (e.expr)
        if e.template is not None: return "{} (&& {})".format (
                self.template_decl (e.template.decl), self.and_expr (e.template.expr))
    def or_elem (self, e):
        if e.expr is not None: return self.and_expr (e.expr)
        if e.template is not None: return "{} (|| {})".format (
                self.template_decl (e.template.decl), self.and_expr (e.template.expr))

class ExpandedExprPrinter (CommonExprPrinter):
    """ Collections of str(expr) functions for an expanded ast """
    def name (self, n):
        return n
    def and_elem (self, e):
        return self.bool_expr (e)
    def or_elem (self, e):
        return self.and_expr (e)

# Ast final printer
class ExpandedAstPrinter (ExpandedExprPrinter):
    def write (self, stream, ast):
        def line (fmt, *args):
            stream.write (fmt.format (*args) + "\n")
        def line_proc_expr_construct (s, name):
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

# Text evaluation
class ExpandedExprTextEval:
    def not_allowed (self, what):
        raise TemplateError ("{} are not allowed in text evaluation".format (what))

    def ref (self, s):
        if s.array is not None: self.not_allowed ("arrays")
        if s.var is not None: return s.var.name
    def rvalue (self, v):
        if v.ref is not None: return self.ref (v.ref)
        if v.const is not None: return v.const
    def expr (self, e):
        if e.val is not None: return self.rvalue (e.val)
        if e.op is not None: self.not_allowed ("+/- operations")
    def comp_expr (self, c):
        try: func = { "=": operator.eq, "<>": operator.ne }[c.op]
        except KeyError: self.not_allowed ("{} operations".format (c.op)) 
        return func (self.expr (c.lhs), self.expr (c.rhs))
    def bool_expr (self, e):
        if e.forall is not None: self.not_allowed ("forall constructs")
        if e.comp is not None: return self.comp_expr (e.comp)
    def and_expr (self, a):
        return all (map (self.bool_expr, a))
    def or_expr (self, o):
        return any (map (self.and_expr, o))

# Template instance generator
class TemplateInstanceGenerator:
    """
    Class to handle template instance generation and template expansion

    An instance/context is a tuple, elements can be refered to by indexes
    in templates expressions
    """
    def __init__ (self, engine, instances_data):
        self.data = instances_data
        self.engine = engine
        self.tep = TemplateExprPrinter ()
        self.text_eval = ExpandedExprTextEval ()

    # Instance constructors
    def empty (self):
        return tuple ()
    def single (self, v):
        return (v,)

    # Template expansion
    def expand (self, tpl, context):
        """ Expand a template expr in the given context """
        try:
            if tpl.arg is not None:
                try: return self.data[tpl.arg]
                except TypeError: raise TemplateError ("wrong data format")
                except KeyError: raise TemplateError ("name {} not found in input data".format (tpl.arg))
            def get_ref (index, field = "_key"):
                try:
                    n = int (index)
                    return context[n][field]
                except IndexError:
                    raise TemplateError ("index {} undefined (defined = {})".format (
                        index, list (range (len (context)))))
                except KeyError:
                    raise TemplateError ("field {} not found in context {}".format (field, context[n]))
            if tpl.key_ref is not None:
                return get_ref (tpl.key_ref)
            if tpl.field_ref is not None:
                return get_ref (tpl.field_ref.key, tpl.field_ref.field)
        except TemplateError as e:
            raise TemplateError ("line {}: in template {}: {}".format (
                line_number (tpl), self.tep.template (tpl), e))
            
    def name (self, name_parts, context):
        try:
            fmt = "{}".join (name_parts[0::2]) # get name_parts and insert format tokens
            expanded = [self.expand (tpl, context) for tpl in name_parts[1::2]]
            name = fmt.format (*expanded)
            if not NAME_FORMAT.match (name):
                raise TemplateError ("malformed: {}".format (name))
            return name
        except TemplateError as e:
            raise TemplateError ("in name {}: {}".format (self.tep.name (name_parts), e))
    
    # Template instantiation
    def instances (self, tpl_decl, context):
        """
        Returns a generator for sub instances formed from a current instance (context)
        and a template declaration node.
        It allows referencing previous index in each declaration.
        It allows to filter instances with a condition
        """
        if tpl_decl is None:
            # No template declaration at all, generate one instance with current context
            yield context
            return

        def normalize (key, dict_ = {}):
            """
            Normalize a template iterable element to a dict with:
            - element keys + _key=element_name if iterable was a dict
            - _key=element if iterable was a list
            """
            normalized = dict (dict_)
            normalized["_key"] = key
            return normalized

        def recursive_generator (tpl_list, ctx):
            if len (tpl_list) == 0:
                # end case, return empty instance
                yield self.empty ()
                return
            # retrieve iterable
            tpl = tpl_list[0]
            iterable = self.expand (tpl, ctx)
            if isinstance (iterable, collections.Mapping):
                iterable = [normalize (k, d) for k, d in iterable.items ()]
            elif isinstance (iterable, collections.Iterable):
                iterable = [normalize (k) for k in iterable]
            else: 
                raise TemplateError ("line {}: in template {}: expanded value is not iterable: {}".format (
                    line_number (tpl), self.tep.template (tpl), iterable))
            # generate sub_instances (make order predictable)
            iterable.sort (key = lambda e: e["_key"])
            for head_ in iterable:
                head = self.single (head_)
                for tail in recursive_generator (tpl_list[1:], ctx + head):
                    yield head + tail

        def eval_cond (context):
            if tpl_decl.cond is None:
                return True
            expanded_cond = self.engine.or_expr (tpl_decl.cond, context)
            return self.text_eval.or_expr (expanded_cond)
        
        tpl_args = [] if tpl_decl.args is None else tpl_decl.args
        for sub_instance in recursive_generator (tpl_args, context):
            instance = context + sub_instance
            if eval_cond (instance):
                yield instance
    
class TemplateEngine:
    """
    Generate a new ast with substituted templates

    Checks for malformed names
    Removes malformed statements due to empty-set iterations
    """
    def __init__ (self, ast):
        self.ast = ast

    def run (self, data):
        self.ig = TemplateInstanceGenerator (self, data)
        return alter (self.ast,
                types = self.types (self.ast.types),
                decls = self.decls (self.ast.decls),
                init = self.proc_expr_construct (self.ast.init, self.ig.empty ()),
                invariants = self.proc_expr_construct_list (self.ast.invariants),
                unsafes = self.proc_expr_construct_list (self.ast.unsafes),
                transitions = self.transitions (self.ast.transitions))

    # Propagate in expressions
    def name (self, n, ctx):
        return self.ig.name (n, ctx)
    def index_list (self, il, ctx):
        return simplify ([self.name (n, ctx) for n in il])
    def array (self, a, ctx):
        return alter_f (a, ctx, name = self.name, index = self.index_list)
    def var (self, v, ctx):
        return alter_f (v, ctx, name = self.name)
    def ref (self, s, ctx):
        if s.array is not None: return alter_f (s, ctx, array = self.array)
        if s.var is not None: return alter_f (s, ctx, var = self.var)
    def rvalue (self, v, ctx):
        if v.ref is not None: return alter_f (v, ctx, ref = self.ref)
        if v.const is not None: return v
    def expr (self, e, ctx):
        if e.val is not None: return alter_f (e, ctx, val = self.rvalue)
        if e.op is not None: return alter_f (e, ctx, lhs = self.rvalue, rhs = self.rvalue)
    def comp_expr (self, c, ctx):
        return alter_f (c, ctx, lhs = self.expr, rhs = self.expr)
    def forall_expr (self, f, ctx):
        if f.comp is not None: return alter_f (f, ctx, comp = self.comp_expr)
        if f.expr is not None: return alter_f (f, ctx, expr = self.or_expr)
    def bool_expr (self, e, ctx):
        if e.forall is not None: return alter_f (e, ctx, forall = self.forall_expr)
        if e.comp is not None: return alter_f (e, ctx, comp = self.comp_expr)
    def and_expr (self, a, ctx):
        generated = []
        for and_elem in a:
            if and_elem.expr is not None:
                generated.append (self.bool_expr (and_elem.expr, ctx))
            if and_elem.template is not None:
                for instance in self.ig.instances (and_elem.template.decl, ctx):
                    generated.extend (self.and_expr (and_elem.template.expr, instance))
        return simplify (generated)
    def or_expr (self, o, ctx):
        generated = []
        for or_elem in o:
            if or_elem.expr is not None:
                generated.append (self.and_expr (or_elem.expr, ctx))
            if or_elem.template is not None:
                for instance in self.ig.instances (or_elem.template.decl, ctx):
                    generated.append (self.and_expr (or_elem.template.expr, instance))
        return simplify (generated)

    # Transitions
    def case (self, c, ctx):
        if c.cond == '_': return alter_f (c, ctx, expr = self.expr)
        else: return alter_f (c, ctx, cond = self.and_expr, expr = self.expr)
    def switch (self, s, ctx):
        generated = []
        for c in s:
            if c.case is not None:
                generated.append (self.case (c, ctx))
            if c.template is not None:
                for instance in self.ig.instances (c.template.decl, ctx):
                    generated.extend (self.switch (c.template.case_list, instance))
        return simplify (generated)
    def assign_value (self, v, ctx):
        if v.switch is not None: return alter_f (v, ctx, switch = self.switch)
        if v.expr is not None: return alter_f (v, ctx, expr = self.expr)
        if v.rand is not None: return v
    def assign (self, u, ctx):
        return alter_f (u, ctx, lhs = self.ref, rhs = self.assign_value)
    def update_list (self, l, ctx):
        generated = []
        for u in l:
            if u.assign is not None:
                generated.append (self.assign (u.assign, ctx))
            if u.template is not None:
                for instance in self.ig.instances (u.template.decl, ctx):
                    generated.extend (self.update_list (u.template.updates, instance))
        return simplify (generated)
    def transition (self, t, ctx):
        # allow require to be null
        # empty updates will remove transition
        return alter_f (alter (t, require = self.or_expr (t.require, ctx)),
                ctx, name = self.name, updates = self.update_list)
    def transitions (self, transitions):
        # allow no transition (cubicle error)
        generated = []
        for t in transitions:
            for instance in self.ig.instances (t.decl, self.ig.empty ()):
                generated.append (self.transition (t, instance))
        return simplify (generated, keep_list = True)
    
    # Var declarations
    def decl (self, d, ctx):
        # typename not a template
        return alter_f (d, ctx, name = self.ref)
    def decls (self, decls):
        # allow no declaration (cubicle error)
        generated = []
        for d in decls:
            for instance in self.ig.instances (d.decl, self.ig.empty ()):
                generated.append (self.decl (d, instance))
        return simplify (generated, keep_list = True)
    
    # Type declarations
    def type_enum_list (self, enum_list, ctx):
        generated = []
        for e in enum_list:
            if e.name is not None:
                generated.append (self.name (e.name, ctx))
            if e.template is not None:
                for instance in self.ig.instances (e.template.decl, ctx):
                    generated.extend (self.type_enum_list (e.template.enum, instance))
        return simplify (generated, keep_list = True) # abstract type (no enum) permitted
    def type_def (self, t, ctx):
        # typename not a template
        return alter_f (t, ctx, enum = self.type_enum_list)
    def types (self, types):
        # allow no types
        return simplify ([self.type_def (t, self.ig.empty ()) for t in types], keep_list = True)

    # Init, unsafe and invariant 
    def proc_expr_construct (self, construct, ctx):
        return alter_f (construct, ctx, expr = self.or_expr)
    def proc_expr_construct_list (self, constructs):
        generated = []
        for c in constructs:
            for instance in self.ig.instances (c.decl, self.ig.empty ()):
                generated.append (self.proc_expr_construct (c, instance))
        return simplify (generated, keep_list = True)

# Exported interface
class CubicleTemplateCompiler:
    """ Main template class. init with template, and run with data and output stream """ 
    def __init__ (self, cin):
        parser = cubicle_parser.CubicleParser (parseinfo = True)
        buf = CubicleBuffer (cin.read ())
        ast = parser.parse (buf, "model")
        self.engine = TemplateEngine (ast)

    def run (self, cout, data):
        ExpandedAstPrinter ().write (cout, self.engine.run (data))

