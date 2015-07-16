Cubicle Template Compiler
=========================

Allows to generates rules, variables, unsafes and expressions by iterating on a set of data.

Why
---

Cubicle is good for checking models with arrays of arbitrary and variable size.
However it is tedious to describe fixed size structures.
In particular, properties between multiple elements of these structures might require the forall_other construct, which might throw false positives.
Duplicating rules can solve these problems, at the cost of generality however.

**ctc** also adds support for nicer syntax, like nested OR.

Installation
------------

Software dependencies:

	python 3
	grako (python 3 library)
	cubicle (model checker)

ctc uses the standard python setuptools for installation (--user for a local install):

	python setup.py install [--user]

If using Vim, `vim/` contains syntax coloring files.

Usage
-----

A simple frontend script is available after installation.
It will compile the templates using json data from a file (see `-h` for options), and run cubicle on the compiled file:

	ctc [options] -- [cubicle options]
	python -m ctc [options] -- [cubicle options]

It can also be used as a python library.
In this case the data needs to be passed as a hierarchy of Mapping-capable or Iterable objects (dict and list are ok):

	import ctc
	ctc.Compiler (...).run (...)

Language and Data format
------------------------

The template language is described in `ctc/cubicle.ebnf`, as a grammar with some comments.
Cubicle templates closely follows cubicle's syntax, while adding some template constructs delimited by '@' characters.

`example/owm` provides an example for a cache coherence protocol linked to a task graph execution model.


