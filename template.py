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

class TemplateError (Exception):
    pass

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
class ExprPrinterCommon:
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

class ExprPrinterRaw (ExprPrinterCommon):
    """ Collections of str(expr) functions for an ast before expansion """
    def template (self, t):
        if t.arg is not None: return t.arg
        if t.key_ref is not None: return t.key_ref
        if t.field_ref is not None: return "{}.{}".format (t.field_ref.key, t.field_ref.field)
    def template_args (self, a):
        return "@{}@".format (", ".join (map (self.template, a)))
    def name (self, n): # template name
        name_parts = n[:]
        name_parts[1::2] = map ("@{}@".format, map (self.template, name_parts[1::2]))
        return "".join (name_parts)
    def and_elem (self, e):
        if e.expr is not None: return self.bool_expr (e.expr)
        if e.template is not None: return "{} (&& {})".format (
                self.template_args (e.template.template), self.and_expr (e.template.expr))
    def or_elem (self, e):
        if e.expr is not None: return self.and_expr (e.expr)
        if e.template is not None: return "{} (|| {})".format (
                self.template_args (e.template.template), self.and_expr (e.template.expr))

class ExprPrinterExpanded (ExprPrinterCommon):
    """ Collections of str(expr) functions for an expanded ast """
    def name (self, n):
        return n
    def and_elem (self, e):
        return self.bool_expr (e)
    def or_elem (self, e):
        return self.and_expr (e)

# Ast final printer
class AstPrinterExpanded (ExprPrinterExpanded):
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

# Exported template engine class
class TemplateEngine:
    """ Main template class. init with template, and run with data and output stream """ 
    def __init__ (self, cin):
        parser = cubicle_parser.CubicleParser (parseinfo = True)
        buf = CubicleBuffer (cin.read ())
        self.ast = parser.parse (buf, "model")

    def run (self, cout, data):
        AstPrinterExpanded ().write (cout, self.substitute (data))

    def substitute (self, data):
        """
        Generate a new ast with substituted templates

        Checks for malformed names
        Removes malformed statements due to empty-set iterations
        """
        # Utils
        NAME_FORMAT = re.compile ("^[A-Za-z][A-Za-z0-9_]*$")
        def line (node):
            return node.parseinfo.buffer.line_info (node.parseinfo.pos).line + 1

        # Ast manipulation
        def alter (node, **kwargs):
            """ copy and update AST node with new args """
            new = dict (node)
            new.update (**kwargs)
            return grako.ast.AST (new)
        def alter_f (node, instance, **funcs):
            """
            Fast copy and update for expressions, calls f(key, instance) for all given key=f
            If f returns None, returns None (recursively delete empty constructs)
            """
            new = dict (node)
            for field, func in funcs.items ():
                new[field] = func (node[field], instance)
                if new[field] is None:
                    return None
            return grako.ast.AST (new)
        def simplify (l, keep_list = False):
            """ Removes None's elements in a list, and returns None if empty """
            cleaned = [e for e in l if e is not None]
            return cleaned if len (cleaned) > 0 or keep_list else None

        # Template condition evaluation
        def eval_cond (cond, instance):
            def not_allowed (what):
                raise TemplateError ("{} are not allowed in condition".format (what))
            def eval_ref (s):
                if s.array is not None: not_allowed ("arrays")
                if s.var is not None: return s.var.name
            def eval_rvalue (v):
                if v.ref is not None: return eval_ref (v.ref)
                if v.const is not None: return v.const
            def eval_expr (e):
                if e.val is not None: return rvalue (e.val)
                if e.op is not None: not_allowed ("+/- operations")
            def eval_comp_expr (c):
                try: func = { "=": operator.eq, "<>": operator.ne }[c.op]
                except KeyError: not_allowed ("{} operations".format (c.op)) 
                return func (eval_expr (c.lhs), eval_expr (c.rhs))
            def eval_bool_expr (e):
                if e.forall is not None: not_allowed ("forall constructs")
                if e.comp is not None: return eval_comp_expr (e.comp)
            def eval_and_expr (a):
                return all (map (eval_bool_expr, a))
            def eval_or_expr (o):
                return any (map (eval_and_expr, o))
            expanded_cond = gen_or_expr (cond, instance)
            return expanded_cond is None or eval_or_expr (expanded_cond) 

        # Template substitution
        def expand_template (t, instance):
            try:
                if t.arg is not None:
                    try: return data[t.arg]
                    except TypeError: raise TemplateError ("wrong data format")
                    except KeyError: raise TemplateError ("arg {} not found in input data".format (t.arg))
                def get_ref (index, field = "_key"):
                    try:
                        n = int (index)
                        return instance[n][field]
                    except IndexError:
                        raise TemplateError ("instance index {} undefined (defined = {})".format (
                            index, list (range (len (instance)))))
                    except KeyError:
                        raise TemplateError ("field {} not found in instance {}".format (field, instance[n]))
                if t.key_ref is not None:
                    return get_ref (t.key_ref)
                if t.field_ref is not None:
                    return get_ref (t.field_ref.key, t.field_ref.field)
            except TemplateError as e:
                raise TemplateError ("line {}: {}".format (line (t), e))
                
        def template_instances (node, instance = tuple ()):
            """
            Returns a generator for sub instances formed from a current instance (context)
            and a template declaration node.
            It allows referencing previous index in each declaration.
            It allows to filter instances with a condition
            """
            def normalize (key, dict_ = {}):
                # normalize an expanded template argument to a dict with _key storing the element key or simple value
                normalized = dict (dict_)
                normalized["_key"] = key
                return normalized
            def instance_generator_rec (t_list, inst):
                if len (t_list) == 0:
                    # end case, return empty instance
                    yield tuple ()
                else:
                    # retrieve iterable
                    try:
                        iterable = expand_template (t_list[0], inst)
                        if isinstance (iterable, collections.Mapping):
                            iterable = [normalize (k, d) for k, d in iterable.items ()]
                        elif isinstance (iterable, collections.Iterable):
                            iterable = [normalize (k) for k in iterable]
                        else: 
                            raise TemplateError ("template value is not iterable: {}".format (iterable))
                        iterable.sort (key = lambda e: e["_key"])
                    except TemplateError as e:
                        raise TemplateError ("in declaration @{}@: {}".format (template_str (t_list[0]), e))
                    # generate sub_instances
                    for head_ in iterable:
                        head = (head_,)
                        for tail in instance_generator_rec (t_list[1:], inst + head):
                            yield head + tail
            for sub_instance in instance_generator_rec ([] if node.template is None else node.template, instance):
                complete_instance = instance + sub_instance
                if node.cond is None or eval_cond (node.cond, complete_instance):
                    yield complete_instance
        
        def gen_name (name_elements, instance):
            try:
                fmt = "{}".join (name_elements[0::2]) # get name_parts and insert format tokens
                expanded = [expand_template (t, instance) for t in name_elements[1::2]]
                name = fmt.format (*expanded)
                if not NAME_FORMAT.match (name):
                    raise TemplateError ("malformed: {}".format (name))
                return name
            except TemplateError as e:
                raise TemplateError ("in name {}: {}".format (template_name_str (name_elements), e))
        
        # Propagate in expressions
        def gen_index_list (l, instance):
            return simplify ([gen_name (i, instance) for i in l])
        def gen_array (a, instance):
            return alter_f (a, instance, name = gen_name, index = gen_index_list)
        def gen_var (v, instance):
            return alter_f (v, instance, name = gen_name)
        def gen_ref (s, instance):
            if s.array is not None: return alter_f (s, instance, array = gen_array)
            if s.var is not None: return alter_f (s, instance, var = gen_var)
        def gen_rvalue (v, instance):
            if v.ref is not None: return alter_f (v, instance, ref = gen_ref)
            if v.const is not None: return v
        def gen_expr (e, instance):
            if e.val is not None: return alter_f (e, instance, val = gen_rvalue)
            if e.op is not None: return alter_f (e, instance, lhs = gen_rvalue, rhs = gen_rvalue)
        def gen_comp_expr (c, instance):
            return alter_f (c, instance, lhs = gen_expr, rhs = gen_expr)
        def gen_forall_expr (f, instance):
            if f.comp is not None: return alter_f (f, instance, comp = gen_comp_expr)
            if f.expr is not None: return alter_f (f, instance, expr = gen_or_expr)
        def gen_bool_expr (e, instance):
            if e.forall is not None: return alter_f (e, instance, forall = gen_forall_expr)
            if e.comp is not None: return alter_f (e, instance, comp = gen_comp_expr)
        def gen_and_expr (a, instance):
            generated = []
            for and_elem in a:
                if and_elem.expr is not None:
                    generated.append (gen_bool_expr (and_elem.expr, instance))
                if and_elem.template is not None:
                    for new in template_instances (and_elem.template, instance):
                        generated.extend (gen_and_expr (and_elem.template.expr, new))
            return simplify (generated)
        def gen_or_expr (o, instance):
            generated = []
            for or_elem in o:
                if or_elem.expr is not None:
                    generated.append (gen_and_expr (or_elem.expr, instance))
                if or_elem.template is not None:
                    for new in template_instances (or_elem.template, instance):
                        generated.append (gen_and_expr (or_elem.template.expr, new))
            return simplify (generated)

        # Transitions
        def gen_case (c, instance):
            if c.cond == '_': return alter_f (c, instance, expr = gen_expr)
            else: return alter_f (c, instance, cond = gen_and_expr, expr = gen_expr)
        def gen_switch (s, instance):
            generated = []
            for c in s:
                if c.case is not None:
                    generated.append (gen_case (c, instance))
                if c.template is not None:
                    for new in template_instances (c.template, instance):
                        generated.extend (gen_switch (c.template.case_list, new))
            return simplify (generated)
        def gen_assign_value (v, instance):
            if v.switch is not None: return alter_f (v, instance, switch = gen_switch)
            if v.expr is not None: return alter_f (v, instance, expr = gen_expr)
            if v.rand is not None: return v
        def gen_assign (u, instance):
            return alter_f (u, instance, lhs = gen_ref, rhs = gen_assign_value)
        def gen_update_list (l, instance):
            generated = []
            for u in l:
                if u.assign is not None:
                    generated.append (gen_assign (u.assign, instance))
                if u.template is not None:
                    for new in template_instances (u.template, instance):
                        generated.extend (gen_update_list (u.template.updates, new))
            return simplify (generated)
        def gen_transition (t, instance):
            # allow require to be null
            # empty updates will remove transition
            return alter_f (alter (t, require = gen_or_expr (t.require, instance)),
                    instance, name = gen_name, updates = gen_update_list)
        def gen_transitions (transitions):
            generated = []
            for t in transitions:
                for instance in template_instances (t):
                    generated.append (gen_transition (t, instance))
            return simplify (generated)
        
        # Var declarations
        def gen_decl (d, instance):
            # typename not a template
            return alter_f (d, instance, name = gen_ref)
        def gen_decls (decls):
            generated = []
            for d in decls:
                for instance in template_instances (d):
                    generated.append (gen_decl (d, instance))
            return simplify (generated)
        
        # Type declarations
        def gen_type_enum_list (enum_list, instance):
            generated = []
            for e in enum_list:
                if e.name is not None:
                    generated.append (gen_name (e.name, instance))
                if e.template is not None:
                    for new in template_instances (e.template, instance):
                        generated.extend (gen_type_enum_list (e.template.enum, new))
            return simplify (generated, keep_list = True) # abstract type (no enum) permitted
        def gen_type (t, instance):
            # typename not a template
            return alter_f (t, instance, enum = gen_type_enum_list)
        def gen_types (types):
            return simplify ([gen_type (t, tuple ()) for t in types], keep_list = True)

        # Init, unsafe and invariant 
        def gen_proc_expr_construct (construct, instance = tuple ()):
            return alter_f (construct, instance, expr = gen_or_expr)
        def gen_proc_expr_construct_list (constructs, keep_list = False):
            generated = []
            for c in constructs:
                for instance in template_instances (c):
                    generated.append (gen_proc_expr_construct (c, instance))
            return simplify (generated, keep_list = keep_list)

        # Main
        new_ast = alter (self.ast,
                types = gen_types (self.ast.types),
                decls = gen_decls (self.ast.decls),
                init = gen_proc_expr_construct (self.ast.init),
                invariants = gen_proc_expr_construct_list (self.ast.invariants, keep_list = True),
                unsafes = gen_proc_expr_construct_list (self.ast.unsafes),
                transitions = gen_transitions (self.ast.transitions))
        if new_ast.decls is None:
            raise TemplateError ("no variable declaration in output")
        if new_ast.init is None:
            raise TemplateError ("init body is empty")
        if new_ast.unsafes is None:
            raise TemplateError ("no unsafe statement")
        if new_ast.transitions is None:
            raise TemplateError ("no transition statement")
        return new_ast

